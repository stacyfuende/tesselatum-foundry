# Foundry asynchronous job and artifact metadata contract

**Status:** Private database foundation, Python/Postgres lifecycle repository, provider-neutral object-store boundary, and Python customer-job orchestration adapter implemented. Hosted API, production worker deployment and a durable object-store provider remain pending.

## Scope

The private `foundry` schema in the existing Panda Roam Supabase project contains three control-plane tables:

- `foundry.jobs`: accepted job and current lifecycle/lease state.
- `foundry.job_events`: append-only lifecycle evidence.
- `foundry.artifacts`: immutable metadata and opaque references to externally stored objects.

Postgres stores bounded request metadata, hashes, state, and object references. It does **not** store source rasters, generated rasters, ZIP bundles, or other artifact bytes. The existing Panda Roam `public` schema is outside this contract.

## Tenant and identity rules

- `tenant_id` and `actor_id` are opaque identifiers resolved by trusted authentication. They must never be accepted from request JSON as authority.
- Every job, event and artifact carries `tenant_id`. Composite foreign keys prevent events/artifacts from being attached to another tenant's job.
- Every repository read/write is tenant-qualified. UUID unpredictability is not authorization.
- `service_role` bypasses Postgres RLS. It is server-only; application code must enforce tenant ownership before every operation.
- Client roles have no schema usage or table privileges. No client-facing RLS policies exist.

## Python repository

The optional psycopg-backed adapter is `tessellatum_foundry.jobs.PostgresJobRepository`; install it with the existing `postgis` extra. Supply a DSN at runtime or a psycopg connection factory. No credentials are embedded in the package.

Implemented operations:

- `submit`: canonical SHA-256 request hashing, tenant-scoped idempotency, and initial event insertion in one transaction.
- `get` and `list_events`: tenant-qualified status and event reads.
- `claim_next`: atomic `FOR UPDATE SKIP LOCKED` claim, fresh lease token, attempt increment, and event insertion.
- `heartbeat`, `complete`, and `fail`: lease-token and expiry fencing; lifecycle state and event changes commit together.
- `reap_expired_leases`: expired leases are atomically requeued or timed out according to the attempt limit.
- `record_artifact`: records metadata and an opaque object key only; it does not upload or store bytes.

Request metadata rejects common credential/source-byte fields and non-finite JSON numbers. The request digest includes request version and the complete semantic metadata envelope. The caller remains responsible for including source checksums and product/implementation versions in that envelope.

## Idempotent submission

1. Normalize and validate the semantic request envelope.
2. Include source checksum and product/version selection in the envelope.
3. Compute SHA-256 over canonical JSON (sorted keys, compact separators, UTF-8).
4. Insert the job using trusted tenant/actor identity and a caller-supplied idempotency key.
5. A duplicate key with the same digest returns the existing job; a different digest raises an idempotency conflict.
6. Insert the initial event in the same transaction as job creation.

Never store bearer credentials, secrets, or source contents in request payloads, errors, manifests, or event details.

## Lifecycle and worker leases

Allowed states are `queued → running → succeeded | failed | cancelled | timed_out`. Retryable failures are requeued only while attempts remain. Each claim increments `attempt_count`; each lease receives a fresh random token and expiry.

Every heartbeat/completion/failure compares tenant, job ID, active status, lease token and lease expiry. Stale workers cannot change state through the repository. The reaper fences expired workers. State updates and event insertions are atomic. No database transaction is held during spatial execution.

## Artifact publication

- Upload bytes to an approved object store before inserting metadata.
- Store opaque object key, tenant/job association, media type, format, byte count, SHA-256, timestamps and non-sensitive metadata only.
- Resolve object keys through a server-side tenant-authorized adapter; never return raw bucket URLs or service credentials.
- Verify checksum and byte count before marking a product delivered.
- Artifact rows are immutable to the application role (select/insert only).
- Expiration/deletion requires a separately controlled retention process. `expires_at` alone does not delete anything.

The repository's metadata insert is not proof that an object exists or has been verified; the future storage adapter must perform that verification before calling it.

## Database privilege boundary

RLS is enabled and forced on all three tables. Client-role access is revoked. Explicit application-role grants are:
- jobs: select/insert/update;
- job events: select/insert;
- artifacts: select/insert;
- identity sequence: usage/select only.

No default table or sequence privileges are granted to the application role. Each future migration must explicitly grant only what its objects require. The service role cannot create schema objects and has no table delete privilege.

## Verification and remaining release gates

The repository has unit coverage for canonical hashing and rejection of sensitive/non-finite metadata. Opt-in Postgres integration tests cover idempotency, cross-tenant read isolation, atomic lifecycle events, claim/complete and stale-lease fencing. CI supplies its own ephemeral PostGIS database to those tests; the fixture refuses to overwrite an existing `foundry` schema and removes only the schema it created.

Still required before a customer pilot:
- request-scoped asynchronous API submission/status/events/download endpoints, preserving the existing synchronous endpoint until a compatibility migration is designed;
- approved durable external object-store provider and retention controls;
- hosted worker process and durable tenant runtime integration with the existing spatial product pipeline;
- authentication integration proving actor/tenant identity comes only from trusted auth;
- production deployment, observability, backup/restore and security controls;
- verification of Supabase Data API exposed-schema configuration. Do not add `foundry` to the exposed schema list.

This is a database and repository foundation, not yet a functioning hosted asynchronous service.
