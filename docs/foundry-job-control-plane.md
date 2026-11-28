# Foundry asynchronous job and artifact metadata contract

**Status:** Database control-plane foundation provisioned; worker/API integration remains pending.

## Scope

The private `foundry` schema in the existing Panda Roam Supabase project contains three control-plane tables:

- `foundry.jobs`: one accepted job and its current lifecycle/lease state.
- `foundry.job_events`: append-only lifecycle evidence.
- `foundry.artifacts`: immutable metadata and opaque references to externally stored objects.

Postgres stores bounded request metadata, hashes, state, and object references. It does **not** store source rasters, generated rasters, ZIP bundles, or other artifact bytes. The existing Panda Roam `public` schema is outside this contract.

## Tenant and identity rules

- `tenant_id` and `actor_id` are opaque identifiers resolved by trusted authentication. They are never accepted from request JSON as authority.
- Every job, event and artifact carries `tenant_id`. Composite foreign keys prevent an event/artifact from being attached to a job belonging to another tenant.
- Every repository operation must include the authenticated tenant in its predicate. UUID unpredictability is not authorization.
- `service_role` bypasses Postgres RLS. It is server-only; application code must enforce tenant ownership before every read/write.
- Client roles have no schema usage or table privileges. No client-facing RLS policies exist.

## Idempotent submission

1. Normalize and validate the request envelope.
2. Compute SHA-256 over a canonical representation of the complete semantic request, including source checksum and product/version selection.
3. Insert the job with trusted tenant/actor, idempotency key, request version, digest, and bounded metadata in one transaction.
4. On duplicate `(tenant_id, idempotency_key)`, compare digests: same digest returns the existing job; different digest is an idempotency conflict.
5. Insert the initial event in the same transaction as job creation.

Never store bearer credentials, secrets, or source contents in request payloads, errors, manifests, or event details.

## Lifecycle and worker leases

Allowed states are `queued → running → succeeded | failed | cancelled | timed_out`. A retryable failure may be explicitly requeued by trusted orchestration, with a new event and cleared terminal timestamp/lease. Increment `attempt_count` for each claim and enforce `max_attempts`.

A worker claim must be atomic and concurrency-safe: select eligible queued rows with `FOR UPDATE SKIP LOCKED`; transition to running with a fresh random lease token and expiry; increment attempts; append the event in the same short transaction; commit before spatial execution.

Every heartbeat/completion/failure must compare job ID and current lease token. Stale workers must not publish outputs or change state. State updates and event insertions are atomic. Never hold a database transaction open during raster/vector execution.

## Artifact publication

- Upload bytes to an approved object store before inserting metadata.
- Store opaque object key, tenant/job association, media type, format, byte count, SHA-256, timestamps and non-sensitive metadata only.
- Resolve object keys through a server-side tenant-authorized adapter; never return raw bucket URLs or service credentials.
- Verify checksum and byte count before marking a product delivered.
- Artifact rows are immutable to the application role (select/insert only).
- Expiration/deletion requires a separately controlled retention process. `expires_at` alone does not delete anything.

## Database privilege boundary

RLS is enabled and forced on all three tables. Client-role access is revoked. Explicit application-role grants are:
- jobs: select/insert/update;
- job events: select/insert;
- artifacts: select/insert;
- identity sequence: usage/select only.

No default table or sequence privileges are granted to the application role. Each future migration must explicitly grant only what its objects require. The service role cannot create schema objects and has no table delete privilege.

## Implemented versus outstanding

Implemented:
- tenant-scoped jobs, events and artifact metadata tables;
- idempotency uniqueness and tenant-composite foreign keys;
- worker lease fields and queue indexes;
- RLS enabled and forced;
- client-role access revoked;
- least-privilege explicit grants and hardened default privileges.

Still required before a customer pilot:
- Python/Postgres repository with tenant-qualified queries and transaction tests;
- API submission/status/download endpoints and canonical request hashing;
- atomic claim, heartbeat, stale-worker fencing, retry/reaper behavior;
- durable external object-store adapter and lifecycle controls;
- worker process, deployment and observability controls;
- negative cross-tenant tests;
- verification of Supabase Data API exposed-schema configuration. Do not add `foundry` to the exposed schema list.

This is a durable metadata foundation, not yet a functioning hosted asynchronous service.
