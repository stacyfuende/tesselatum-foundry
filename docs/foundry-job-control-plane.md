# Foundry asynchronous job and artifact metadata contract

**Status:** Database control-plane foundation provisioned; worker/API integration remains pending.

## Scope

The private `foundry` schema in the existing Panda Roam Supabase project contains three control-plane tables:

- `foundry.jobs`: one accepted customer job and its current lifecycle/lease state.
- `foundry.job_events`: append-only lifecycle evidence for each job.
- `foundry.artifacts`: immutable metadata and opaque references to externally stored objects.

Postgres stores bounded request metadata, hashes, state, and object references. It does **not** store GeoJSON uploads, raster sources, generated rasters, ZIP bundles, or other artifact bytes. The existing Panda Roam `public` schema is not part of this contract.

## Tenant and identity rules

- `tenant_id` and `actor_id` are opaque identifiers resolved by the trusted authentication layer. They are never accepted from request JSON as authority.
- Every job, event and artifact carries `tenant_id`. Composite foreign keys prevent an artifact/event from being attached to a job belonging to another tenant.
- Every repository operation must include the authenticated tenant in its predicate, including lookup by job ID, idempotency key, artifact ID, or object key. UUID unpredictability is not authorization.
- `service_role` bypasses Postgres RLS. It is server-only and must never appear in browser code. The application must enforce tenant ownership before every read/write even though RLS is enabled and forced on all three tables.
- Client roles have no schema usage or table privileges. There are no client-facing RLS policies.

## Idempotent submission

The idempotency scope is `(tenant_id, idempotency_key)`.

1. Normalize and validate the request envelope before persistence.
2. Compute SHA-256 over a canonical representation of the complete semantic request, including source-object checksum and product/version selection. Do not hash an unstable JSON serialization.
3. Insert the job with the trusted tenant/actor, key, request version, digest, and bounded request metadata in one transaction.
4. If the unique key already exists, compare the stored digest:
   - same digest: return the existing job representation; do not enqueue a second execution;
   - different digest: return an idempotency conflict; never silently reuse the old job for a different request.
5. Insert the initial `job_events` record in the same transaction as job creation.

Do not put raw bearer credentials, secrets, or source contents in `request_payload`, `last_error`, `result_manifest`, or event details.

## Lifecycle and worker leases

Allowed states are:

`queued → running → succeeded | failed | cancelled | timed_out`

A retryable failure may be explicitly requeued by trusted orchestration, with a new event and a cleared terminal timestamp/lease. Increment `attempt_count` for each claim; enforce `max_attempts`. Never infer retryability from a free-form error message.

A worker claim must be atomic and concurrency-safe:

- select eligible queued rows with `available_at <= now()`;
- use `FOR UPDATE SKIP LOCKED` in a short transaction;
- transition the selected job to `running`, set a fresh random `lease_token`, `lease_expires_at`, `started_at` if first start, increment `attempt_count`, and update `updated_at`;
- append the corresponding event in the same transaction;
- commit before executing spatial work.

All worker heartbeats/completions/failures must compare both `job_id` and the current `lease_token`. A stale worker whose lease has expired or been replaced must not publish outputs or change state. A reaper may requeue or time out expired leases according to the job's attempt policy. Never hold a database transaction open during raster/vector execution.

State updates and their event insertions must be atomic. Enforce legal transitions in the repository/service layer using conditional updates on the expected current state and lease token; a zero-row update is a conflict, not success.

## Artifact publication

- Upload bytes to an approved object store before inserting artifact metadata.
- Store only opaque `object_key`, tenant/job association, media type, format, byte count, SHA-256, timestamps and non-sensitive metadata.
- Object keys are not public URLs. Resolve them through a server-side tenant-authorized storage adapter; never return a raw bucket URL or service credential.
- Verify object checksum and byte count before marking a product delivered.
- Treat artifact records as immutable. The application role can select/insert artifact rows but cannot update/delete them.
- Expiration and deletion require a separately controlled retention process that removes object bytes and metadata consistently and records an auditable outcome. No automatic deletion is implied by `expires_at`.

## Database privilege boundary

The migration enables and forces RLS on all three tables, revokes client-role privileges, and grants the server role only the operations needed by the contract:
- jobs: select/insert/update;
- job events: select/insert (append-only for the application role);
- artifacts: select/insert (immutable for the application role).

The service role receives no table delete privilege and no ability to create schema objects. Database owners/migration operators remain privileged and must be tightly controlled.

## Implemented versus outstanding

Implemented in the database and migration:
- tenant-scoped job, event and artifact metadata tables;
- idempotency uniqueness constraint;
- tenant-composite foreign keys;
- worker lease fields and queue indexes;
- RLS enabled and forced;
- client-role access revoked;
- application-role grants limited to the operations above.

Still required before a customer pilot:
- a Python/Postgres repository with tenant-qualified queries and transaction tests;
- API submission/status/download endpoints and canonical request hashing;
- atomic job claim, lease heartbeat, stale-worker fencing, retry/reaper behavior;
- a durable external object-store adapter with per-tenant authorization and lifecycle controls;
- an actual worker process and deployment/observability controls;
- negative tests for cross-tenant job, event, artifact and object access;
- verification of the Supabase Data API exposed-schema configuration. The database role grants already deny `anon` and `authenticated` access to `foundry`; do not add this schema to the exposed schema list.

This is a durable metadata foundation, not yet a functioning hosted asynchronous service.
