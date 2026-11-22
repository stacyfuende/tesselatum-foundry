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
