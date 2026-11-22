-- Integration smoke test for migration 0002.
-- Run after migrations 0001 and 0002 on a disposable PostGIS database.
-- All fixture rows are rolled back.

BEGIN;

DO $foundry_test$
DECLARE
    v_dataset uuid;
    v_snapshot uuid;
    v_record_inline uuid;
    v_record_external uuid;
BEGIN
    INSERT INTO foundry.source_dataset
        (source_key, title, registered_by)
    VALUES
        ('test:bulk-source-boundary', 'Bulk source boundary fixture', 'migration-test')
    RETURNING source_dataset_id INTO v_dataset;

    INSERT INTO foundry.source_snapshot
        (source_dataset_id, snapshot_key, object_uri, object_version,
         storage_format, checksum_hex, byte_size)
    VALUES
        (v_dataset, 'bulk-fixture-001',
         's3://foundry-test/landing/roads/source.parquet',
         'version-fixture-1', 'parquet',
         repeat('a', 64), 12345)
    RETURNING source_snapshot_id INTO v_snapshot;

    INSERT INTO foundry.source_record
        (source_snapshot_id, source_record_key, payload)
    VALUES
        (v_snapshot, 'small-record',
         '{"road_class":"local"}'::jsonb)
    RETURNING source_record_id INTO v_record_inline;

    INSERT INTO foundry.source_record
        (source_snapshot_id, source_record_key, payload_ref)
    VALUES
        (v_snapshot, 'large-feature',
         '{"object_uri":"s3://foundry-test/landing/roads/source.parquet","feature_id":"road-991"}'::jsonb)
    RETURNING source_record_id INTO v_record_external;

    IF v_record_inline IS NULL OR v_record_external IS NULL THEN
        RAISE EXCEPTION 'expected inline and object-referenced source records';
    END IF;

    -- A record cannot omit both payload forms.
    BEGIN
        INSERT INTO foundry.source_record
            (source_snapshot_id, source_record_key)
        VALUES
            (v_snapshot, 'missing-payload');
        RAISE EXCEPTION 'source record without payload or locator was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    -- A record cannot store both forms and create ambiguous source-of-truth semantics.
    BEGIN
        INSERT INTO foundry.source_record
            (source_snapshot_id, source_record_key, payload, payload_ref)
        VALUES
            (v_snapshot, 'ambiguous-payload', '{}'::jsonb, '{}'::jsonb);
        RAISE EXCEPTION 'source record with both payload forms was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END
$foundry_test$;

ROLLBACK;
