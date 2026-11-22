# Database migrations and integration checks

The spatial information core uses PostgreSQL and PostGIS. Its first migration is additive and creates the `foundry` schema without modifying the existing filesystem-backed Artifact, definition, or Run stores.

## Requirements

- PostgreSQL 15 or newer recommended.
- PostGIS 3.3 or newer recommended.
- A database role permitted to create the PostGIS extension and schema objects.

## Apply migrations in order

Use a disposable database first:

```bash
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/migrations/0001_spatial_information_core.sql
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/migrations/0002_bulk_object_storage_boundary.sql
```

## Python repository adapter

Install the optional database dependency:

```bash
pip install 'tessellatum-foundry[postgis]'
```

The adapter accepts an already-open psycopg 3 connection. It does not create a pool, read credentials, or commit individual writes implicitly:

```python
import psycopg
from tessellatum_foundry.information import PostgresInformationStore

with psycopg.connect(FOUNDRY_DATABASE_URL) as connection:
    store = PostgresInformationStore(connection)
    with store.transaction():
        road = store.create_entity(
            entity_type="RoadSegment",
            created_by="road-network-import",
        )
        # Register source dataset/snapshot/record, crosswalk, observation,
        # representation and relationships in this same transaction.
```

Use `add_representation` with WKB bytes and an explicit positive SRID. The adapter uses parameterized SQL and PostgreSQL JSONB adaptation; geometry is constructed by PostGIS. Transaction ownership remains with the caller so a complete import batch can succeed or roll back atomically.

The first adapter exposes focused writes for entities, source datasets/snapshots/records, source crosswalks, observations, representations, and relationships, plus exact entity lookup. It is an initial persistence interface—not yet a complete ingestion pipeline, query API, authentication boundary, or production service.

## Large source data

Migration 0002 adds durable object references to source snapshots and lets a source record contain either compact inline JSON or a locator into the immutable snapshot object. For large data, upload and checksum the source object first, register its stable object URI/version, then store feature/row locators rather than copying full geometries into JSONB.

The object URI must not contain credentials or expiring signed query parameters. Store only non-secret storage metadata in the database. Migration 0002 is additive and preserves existing inline source-record payloads.

See [storage and processing architecture](../docs/STORAGE_AND_PROCESSING_ARCHITECTURE.md) and [ADR-046](../docs/decisions/046-bulk-geospatial-storage.md).

## Stream source objects

The core package includes an S3-compatible streaming uploader that accepts an injected client, so credentials, endpoint configuration, retries, and SDK lifecycle remain with the deployment. It reads bounded chunks, switches to multipart upload for large streams, and returns a SHA-256 checksum, byte count, object URI, and provider version/ETag when supplied:

```python
from tessellatum_foundry.storage import S3ObjectStore

objects = S3ObjectStore(s3_client, bucket="foundry-data", part_size=16 * 1024 * 1024)
with open("roads.parquet", "rb") as source:
    receipt = objects.upload_stream(
        source,
        key="landing/import-2026-001/roads.parquet",
        content_type="application/vnd.apache.parquet",
    )
# Register receipt.object_uri and receipt.checksum_sha256 on the source snapshot.
```

The key must be unique for each immutable snapshot attempt. Enforce versioning/no-overwrite and lifecycle rules in the object-store bucket policy; the adapter does not pretend to enforce cloud IAM or bucket policy.

## Run the integration smoke test

After applying the migration:

```bash
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/tests/0001_spatial_information_core.sql
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/tests/0002_bulk_object_storage_boundary.sql
```

The migration 0001 test creates representative source, entity, observation, representation, and relationship records inside a transaction and rolls them back. It checks source-key uniqueness, same-entity representation supersession, positive geometry SRIDs, and the GiST geometry index. The migration 0002 test checks both compact inline payloads and object locators, including rejection of missing or ambiguous payload forms.

Apply both migrations before running the SQL smoke tests. The migration 0001 SQL file has not yet been executed against a live PostgreSQL/PostGIS instance; migration 0002 and its new storage-boundary test are also unverified. Do not mark the migration verified until both commands complete successfully on a disposable database.

## Migration discipline

- Migrations are ordered and applied once; do not edit an already-applied migration in a shared environment. Create a new forward migration for later changes.
- Back up the database before applying migrations outside a disposable environment.
- Never use a production database for the integration smoke test.
- Keep source snapshots and records intact; corrections should add observations and representation versions rather than rewrite history.
- Database role grants, row-level security, append-only enforcement, backup/restore automation, and production migration orchestration are not yet implemented.
