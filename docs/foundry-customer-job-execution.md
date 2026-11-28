# Foundry customer-job execution adapter

**Status:** Python intake and leased worker orchestration implemented on the feature branch. No hosted API, production worker, or approved durable object-store provider is connected.

## Flow

1. The authenticated API layer supplies trusted `tenant_id` and `actor_id`; the request body cannot override either.
2. `submit_customer_product_job` stages source bytes through the `ObjectStore` interface under an opaque tenant namespace.
3. The staged bytes are checked against the store receipt. The repository receives only the validated customer request metadata, object key, SHA-256 and byte count.
4. `PostgresJobRepository.submit` creates an idempotent queued job and its initial event. The source checksum is part of the canonical request envelope.
5. A worker claims one job using the repository's atomic lease operation. A heartbeat renews the lease while spatial processing runs.
6. The worker fetches the source object with a byte limit, re-verifies its checksum, and invokes the existing `run_customer_spatial_product` pipeline using the tenant runtime.
7. Only a product with `status == "delivered"` and ZIP bytes is published. The ZIP is stored immutably, verified, registered in `foundry.artifacts`, and referenced by the completion manifest.
8. Completion, failure and retry transitions remain lease-token fenced. Error metadata records an exception class code only, not raw traces, customer data, paths or credentials.

## Existing pipeline preserved

The worker calls the same `run_customer_spatial_product` function used by the synchronous customer endpoint. It does not create a second product engine, accept customer-supplied capabilities, templates or execution graphs, or bypass the existing acceptance and delivery checks.

The existing synchronous `POST /v1/products` endpoint is unchanged. This adapter is an additional asynchronous path; API routing and customer-facing status/download endpoints are separate release work.

## Idempotency and recovery

- Source object keys include both the idempotency-key digest and source-content digest. Re-submitting the same request is an immutable replay; changing source bytes produces a different staged key and is then rejected by the repository's semantic idempotency check.
- Artifact metadata insertion is idempotent for an existing tenant/object-key pair only when all material metadata matches. A conflicting reuse is rejected.
- A crash after output upload but before job completion can safely retry the same immutable output key and artifact metadata.
- A stale worker cannot complete/fail a job after its lease expires or changes. If lease renewal fails, final repository fencing remains authoritative.
- Retry scheduling and exhausted-attempt behavior remain owned by `PostgresJobRepository`.

## Boundaries that remain open

This implementation is an orchestration adapter, not a hosted service:

- `InMemoryObjectStore` is test-only. No real cloud bucket or provider has been selected or provisioned.
- `LocalTenantRuntimeResolver` remains process-local and filesystem-backed. A hosted multi-worker deployment needs durable tenant runtime/artifact storage or a reviewed adapter with equivalent persistence and isolation.
- The job worker needs a hosting process and private credentials/network configuration. No Vercel deployment or Supabase Data API exposure is enabled by this change.
- Customer-facing asynchronous submit/status/events/download endpoints, artifact authorization, retention/cleanup, observability, and operational recovery procedures remain to be implemented.
- The existing synchronous endpoint must remain available until a deliberate compatibility migration is separately approved.

## Local verification

The new tests use the in-memory store and fakes to verify source staging, checksum metadata, reuse of the existing pipeline contract, verified ZIP publication, artifact registration and refusal to publish rejected products. Postgres lifecycle and idempotency tests remain covered by the existing ephemeral-Postgres CI job.
