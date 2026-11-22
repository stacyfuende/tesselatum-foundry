-- Foundry spatial information core, initial relational model.
-- PostgreSQL 15+ and PostGIS 3.3+ recommended.
-- Apply once to a dedicated database. This migration is additive and does not
-- alter the existing Artifact, Cell, Recipe, or Run storage.

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS foundry;

CREATE TABLE foundry.entity (
    entity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type text NOT NULL CHECK (length(btrim(entity_type)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL CHECK (length(btrim(created_by)) > 0),
    lifecycle_state text NOT NULL DEFAULT 'active'
        CHECK (lifecycle_state IN ('active', 'retired', 'superseded')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(metadata) = 'object')
);

COMMENT ON TABLE foundry.entity IS
    'Stable Foundry identity for a geographic or modeled entity; never derived from a source row or geometry hash.';

CREATE TABLE foundry.source_dataset (
    source_dataset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key text NOT NULL UNIQUE CHECK (length(btrim(source_key)) > 0),
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    provider text,
    description text,
    declared_license text,
    source_uri text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    registered_at timestamptz NOT NULL DEFAULT now(),
    registered_by text NOT NULL CHECK (length(btrim(registered_by)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE foundry.source_snapshot (
    source_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_dataset_id uuid NOT NULL
        REFERENCES foundry.source_dataset(source_dataset_id) ON DELETE RESTRICT,
    snapshot_key text NOT NULL CHECK (length(btrim(snapshot_key)) > 0),
    captured_at timestamptz,
    retrieved_at timestamptz NOT NULL DEFAULT now(),
    source_uri text,
    checksum_algorithm text NOT NULL DEFAULT 'sha256'
        CHECK (checksum_algorithm = 'sha256'),
    checksum_hex char(64),
    media_type text,
    byte_size bigint CHECK (byte_size IS NULL OR byte_size >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_dataset_id, snapshot_key),
    CHECK (checksum_hex IS NULL OR checksum_hex ~ '^[0-9a-fA-F]{64}$'),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE foundry.source_record (
    source_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_snapshot_id uuid NOT NULL
        REFERENCES foundry.source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    source_record_key text NOT NULL CHECK (length(btrim(source_record_key)) > 0),
    source_layer text,
    source_ordinal bigint CHECK (source_ordinal IS NULL OR source_ordinal >= 0),
    payload jsonb NOT NULL,
    payload_checksum char(64),
    ingested_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_snapshot_id, source_record_key),
    CHECK (payload_checksum IS NULL OR payload_checksum ~ '^[0-9a-fA-F]{64}$')
);

CREATE INDEX source_record_snapshot_idx
    ON foundry.source_record (source_snapshot_id);

CREATE TABLE foundry.entity_source_link (
    entity_id uuid NOT NULL
        REFERENCES foundry.entity(entity_id) ON DELETE RESTRICT,
    source_record_id uuid NOT NULL
        REFERENCES foundry.source_record(source_record_id) ON DELETE RESTRICT,
    link_state text NOT NULL DEFAULT 'proposed'
        CHECK (link_state IN ('proposed', 'accepted', 'rejected', 'superseded')),
    match_method text NOT NULL CHECK (length(btrim(match_method)) > 0),
    confidence numeric(5,4)
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    rationale text,
    decided_at timestamptz,
    decided_by text,
    PRIMARY KEY (entity_id, source_record_id),
    CHECK (
        (link_state = 'proposed' AND decided_at IS NULL)
        OR
        (link_state <> 'proposed' AND decided_at IS NOT NULL AND decided_by IS NOT NULL)
    )
);

CREATE INDEX entity_source_link_record_idx
    ON foundry.entity_source_link (source_record_id);

CREATE TABLE foundry.observation (
    observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id uuid NOT NULL
        REFERENCES foundry.entity(entity_id) ON DELETE RESTRICT,
    source_record_id uuid
        REFERENCES foundry.source_record(source_record_id) ON DELETE RESTRICT,
    observation_kind text NOT NULL CHECK (length(btrim(observation_kind)) > 0),
    observed_at timestamptz,
    valid_time tstzrange,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
    assertion jsonb NOT NULL,
    confidence numeric(5,4)
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    supersedes_observation_id uuid,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(assertion) = 'object'),
    CHECK (jsonb_typeof(provenance) = 'object'),
    CHECK (valid_time IS NULL OR NOT isempty(valid_time)),
    UNIQUE (observation_id, entity_id),
    FOREIGN KEY (supersedes_observation_id, entity_id)
        REFERENCES foundry.observation(observation_id, entity_id) ON DELETE RESTRICT
);

CREATE INDEX observation_entity_recorded_idx
    ON foundry.observation (entity_id, recorded_at DESC);
CREATE INDEX observation_source_record_idx
    ON foundry.observation (source_record_id);

CREATE TABLE foundry.entity_representation (
    representation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id uuid NOT NULL
        REFERENCES foundry.entity(entity_id) ON DELETE RESTRICT,
    representation_version integer NOT NULL CHECK (representation_version > 0),
    observation_id uuid,
    geometry geometry(Geometry) NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_time tstzrange,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
    supersedes_representation_id uuid,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (entity_id, representation_version),
    UNIQUE (representation_id, entity_id),
    CHECK (ST_SRID(geometry) > 0),
    CHECK (NOT ST_IsEmpty(geometry)),
    CHECK (jsonb_typeof(attributes) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (valid_time IS NULL OR NOT isempty(valid_time)),
    FOREIGN KEY (observation_id, entity_id)
        REFERENCES foundry.observation(observation_id, entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_representation_id, entity_id)
        REFERENCES foundry.entity_representation(representation_id, entity_id) ON DELETE RESTRICT
);

CREATE INDEX entity_representation_entity_version_idx
    ON foundry.entity_representation (entity_id, representation_version DESC);
CREATE INDEX entity_representation_geometry_gix
    ON foundry.entity_representation USING gist (geometry);
CREATE INDEX entity_representation_observation_idx
    ON foundry.entity_representation (observation_id);

CREATE TABLE foundry.entity_relationship (
    relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity_id uuid NOT NULL
        REFERENCES foundry.entity(entity_id) ON DELETE RESTRICT,
    relationship_type text NOT NULL CHECK (length(btrim(relationship_type)) > 0),
    object_entity_id uuid NOT NULL
        REFERENCES foundry.entity(entity_id) ON DELETE RESTRICT,
    observation_id uuid,
    valid_time tstzrange,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (subject_entity_id <> object_entity_id),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (valid_time IS NULL OR NOT isempty(valid_time)),
    FOREIGN KEY (observation_id, subject_entity_id)
        REFERENCES foundry.observation(observation_id, entity_id) ON DELETE RESTRICT
);

CREATE INDEX entity_relationship_subject_idx
    ON foundry.entity_relationship (subject_entity_id, relationship_type);
CREATE INDEX entity_relationship_object_idx
    ON foundry.entity_relationship (object_entity_id, relationship_type);
CREATE INDEX entity_relationship_observation_idx
    ON foundry.entity_relationship (observation_id);

COMMENT ON TABLE foundry.observation IS
    'Append-only source-backed or user-authored assertion; recorded_at is distinct from observed_at and valid_time.';
COMMENT ON TABLE foundry.entity_representation IS
    'Versioned spatial depiction; geometry is not the identity of the entity.';
COMMENT ON TABLE foundry.entity_relationship IS
    'Typed, directed, time-qualified relationship between stable entity identities.';

COMMIT;
