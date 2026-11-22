-- Integration smoke test for migration 0001.
-- Run after applying the migration to a disposable PostGIS database:
--   psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/tests/0001_spatial_information_core.sql
-- All fixture rows are rolled back at the end.

BEGIN;

DO $foundry_test$
DECLARE
    v_dataset uuid;
    v_snapshot uuid;
    v_record_a uuid;
    v_record_b uuid;
    v_road uuid;
    v_junction uuid;
    v_observation uuid;
    v_representation uuid;
    v_index_exists boolean;
BEGIN
    INSERT INTO foundry.source_dataset
        (source_key, title, registered_by)
    VALUES
        ('test:road-network', 'Road network integration fixture', 'migration-test')
    RETURNING source_dataset_id INTO v_dataset;

    INSERT INTO foundry.source_snapshot
        (source_dataset_id, snapshot_key, media_type)
    VALUES
        (v_dataset, 'fixture-001', 'application/geo+json')
    RETURNING source_snapshot_id INTO v_snapshot;

    INSERT INTO foundry.source_record
        (source_snapshot_id, source_record_key, payload)
    VALUES
        (v_snapshot, 'road-001', '{"type":"Feature","properties":{"class":"local"}}'::jsonb)
    RETURNING source_record_id INTO v_record_a;

    INSERT INTO foundry.source_record
        (source_snapshot_id, source_record_key, payload)
    VALUES
        (v_snapshot, 'road-001-alt', '{"source_id":"road-001-alt"}'::jsonb)
    RETURNING source_record_id INTO v_record_b;

    INSERT INTO foundry.entity (entity_type, created_by)
    VALUES ('RoadSegment', 'migration-test')
    RETURNING entity_id INTO v_road;

    INSERT INTO foundry.entity (entity_type, created_by)
    VALUES ('Junction', 'migration-test')
    RETURNING entity_id INTO v_junction;

    INSERT INTO foundry.entity_source_link
        (entity_id, source_record_id, link_state, match_method, confidence)
    VALUES
        (v_road, v_record_a, 'proposed', 'fixture-exact-source-key', 1.0),
        (v_road, v_record_b, 'proposed', 'fixture-cross-source-match', 0.95);

    UPDATE foundry.entity_source_link
       SET link_state = 'accepted',
           decided_at = now(),
           decided_by = 'migration-test'
     WHERE entity_id = v_road
       AND source_record_id = v_record_a;

    INSERT INTO foundry.observation
        (entity_id, source_record_id, observation_kind, observed_at,
         valid_time, recorded_by, assertion)
    VALUES
        (v_road, v_record_a, 'source_feature_observed', now(),
         tstzrange('2026-01-01 00:00:00+00', '2027-01-01 00:00:00+00', '[)'),
         'migration-test', '{"surface":"unknown"}'::jsonb)
    RETURNING observation_id INTO v_observation;

    INSERT INTO foundry.entity_representation
        (entity_id, representation_version, observation_id, geometry,
         attributes, recorded_by)
    VALUES
        (v_road, 1, v_observation,
         ST_SetSRID(ST_GeomFromText('LINESTRING(36.8 -1.3, 36.81 -1.31)'), 4326),
         '{"road_class":"local"}'::jsonb, 'migration-test')
    RETURNING representation_id INTO v_representation;

    INSERT INTO foundry.entity_representation
        (entity_id, representation_version, observation_id, geometry,
         attributes, recorded_by, supersedes_representation_id)
    VALUES
        (v_road, 2, v_observation,
         ST_SetSRID(ST_GeomFromText('LINESTRING(36.8 -1.3, 36.812 -1.312)'), 4326),
         '{"road_class":"local","corrected":true}'::jsonb,
         'migration-test', v_representation);

    INSERT INTO foundry.entity_relationship
        (subject_entity_id, relationship_type, object_entity_id,
         observation_id, recorded_by)
    VALUES
        (v_road, 'connects_to', v_junction, v_observation, 'migration-test');

    -- Duplicate source keys are rejected within one immutable snapshot.
    BEGIN
        INSERT INTO foundry.source_record
            (source_snapshot_id, source_record_key, payload)
        VALUES
            (v_snapshot, 'road-001', '{}'::jsonb);
        RAISE EXCEPTION 'duplicate source record key was unexpectedly accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    -- A representation cannot supersede a representation of another entity.
    BEGIN
        INSERT INTO foundry.entity_representation
            (entity_id, representation_version, geometry, recorded_by,
             supersedes_representation_id)
        VALUES
            (v_junction, 1, ST_SetSRID(ST_MakePoint(36.8, -1.3), 4326),
             'migration-test', v_representation);
        RAISE EXCEPTION 'cross-entity representation supersession was accepted';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;

    -- Spatial records must carry an explicit positive SRID.
    BEGIN
        INSERT INTO foundry.entity_representation
            (entity_id, representation_version, geometry, recorded_by)
        VALUES
            (v_junction, 1, ST_SetSRID(ST_MakePoint(36.8, -1.3), 0),
             'migration-test');
        RAISE EXCEPTION 'geometry with SRID 0 was unexpectedly accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    SELECT EXISTS (
        SELECT 1
          FROM pg_indexes
         WHERE schemaname = 'foundry'
           AND indexname = 'entity_representation_geometry_gix'
    ) INTO v_index_exists;

    IF NOT v_index_exists THEN
        RAISE EXCEPTION 'expected GiST geometry index was not created';
    END IF;
END
$foundry_test$;

ROLLBACK;
