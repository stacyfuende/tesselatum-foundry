-- Large-source storage boundary for Foundry's spatial information core.
-- Apply after 0001. Raw dataset bytes live in object storage; Postgres stores
-- immutable object identity and compact record locators, not bulk source files.

BEGIN;

ALTER TABLE foundry.source_snapshot
    ADD COLUMN object_uri text,
    ADD COLUMN object_version text,
    ADD COLUMN storage_format text,
    ADD COLUMN storage_options jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE foundry.source_snapshot
    ADD CONSTRAINT source_snapshot_storage_options_object
        CHECK (jsonb_typeof(storage_options) = 'object'),
    ADD CONSTRAINT source_snapshot_object_uri_nonblank
        CHECK (object_uri IS NULL OR length(btrim(object_uri)) > 0),
    ADD CONSTRAINT source_snapshot_object_checksum_required
        CHECK (object_uri IS NULL OR checksum_hex IS NOT NULL),
    ADD CONSTRAINT source_snapshot_storage_format_nonblank
        CHECK (storage_format IS NULL OR length(btrim(storage_format)) > 0);

COMMENT ON COLUMN foundry.source_snapshot.object_uri IS
    'Stable object-store URI for the preserved source bytes; never a credential-bearing or expiring signed URL.';
COMMENT ON COLUMN foundry.source_snapshot.object_version IS
    'Provider object version/generation where supported; combine with checksum for immutable retrieval.';
COMMENT ON COLUMN foundry.source_snapshot.storage_options IS
    'Non-secret storage metadata only; credentials and signed URLs must never be stored here.';

ALTER TABLE foundry.source_record
    ALTER COLUMN payload DROP NOT NULL,
    ADD COLUMN payload_ref jsonb;

ALTER TABLE foundry.source_record
    ADD CONSTRAINT source_record_payload_or_reference
        CHECK (
            (payload IS NOT NULL AND payload_ref IS NULL)
            OR
            (payload IS NULL AND payload_ref IS NOT NULL
             AND jsonb_typeof(payload_ref) = 'object')
        );

COMMENT ON COLUMN foundry.source_record.payload IS
    'Optional compact record payload. Do not duplicate large geometries or full source features here.';
COMMENT ON COLUMN foundry.source_record.payload_ref IS
    'Locator into the immutable snapshot object, e.g. partition/object key plus feature ID or row-group/row offset.';

COMMIT;
