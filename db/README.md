# Database migrations and integration checks

The spatial information core uses PostgreSQL and PostGIS. Its first migration is additive and creates the `foundry` schema without modifying the existing filesystem-backed Artifact, definition, or Run stores.

## Requirements

- PostgreSQL 15 or newer recommended.
- PostGIS 3.3 or newer recommended.
- A database role permitted to create the PostGIS extension and schema objects.

## Apply the initial migration

Use a disposable database first:

```bash
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/migrations/0001_spatial_information_core.sql
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

## Run the integration smoke test

After applying the migration:

```bash
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/tests/0001_spatial_information_core.sql
```

The test creates representative source, entity, observation, representation, and relationship records inside a transaction and rolls them back. It checks source-key uniqueness, same-entity representation supersession, positive geometry SRIDs, and the GiST geometry index.

These SQL files have not yet been executed against a live PostgreSQL/PostGIS instance. Do not mark the migration verified until both commands complete successfully on a disposable database.

## Migration discipline

- Migrations are ordered and applied once; do not edit an already-applied migration in a shared environment. Create a new forward migration for later changes.
- Back up the database before applying migrations outside a disposable environment.
- Never use a production database for the integration smoke test.
- Keep source snapshots and records intact; corrections should add observations and representation versions rather than rewrite history.
- Database role grants, row-level security, append-only enforcement, backup/restore automation, and production migration orchestration are not yet implemented.
