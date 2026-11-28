# ADR-053 — Foundry pre-production hosting boundary

**Status:** Accepted for pre-production; amended 2026-11-28 after inspection and approval to reuse existing Hobby and Supabase resources  
**Date:** 2026-11-28  
**Scope:** Customer web surface, API runtime, execution workers, durable state

## Context

Foundry's customer API is currently a standard-library `ThreadingHTTPServer`. Its authentication and tenant runtime are injected by the host, and its successful response is a synchronous ZIP bundle. The execution path can invoke spatial workers and native dependencies. The current local tenant resolver and filesystem stores are development adapters, not shared production infrastructure.

The Vercel-linked `foundry-product-viewer` project is a static viewer only, not a deployed customer API or worker.

The existing Supabase `panda-roam` project has an established spatial-transit model in `public`. Those tables and the rest of the Panda Roam estate are not Foundry resources and must not be altered. Foundry uses only a separate `foundry` schema. No new paid service or Supabase project is authorized.

## Decisions

1. **Keep the customer viewer on Vercel Hobby as a static web surface.** Preview deployments do not imply a deployed API or worker.
2. **Do not deploy the current threaded HTTP server directly as a Vercel Function.** A request-scoped adapter is required.
3. **Use Vercel Hobby for pre-production and bounded control-plane experiments only.** Hobby Functions have a maximum execution duration of 300 seconds. Do not run long spatial jobs or durable workers inside a Hobby Function. Reassess hosting and terms before commercial service.
4. **Use only the dedicated `foundry` schema in `panda-roam` for Foundry metadata.** The schema is owned by `postgres`; client roles have no schema access; `service_role` has USAGE but not CREATE. The schema is not to be added to Supabase API-exposed schemas. Existing Panda Roam tables, policies, grants, extensions, buckets and functions are outside scope.
5. **Store bounded control-plane metadata only.** Three tables now exist: `foundry.jobs`, `foundry.job_events`, and `foundry.artifacts`. RLS is enabled and forced on all three. `anon` and `authenticated` have no schema/table access. `service_role` has jobs SELECT/INSERT/UPDATE, events SELECT/INSERT, artifacts SELECT/INSERT, and event-sequence USAGE/SELECT only. It has no table DELETE and no schema CREATE. Default table/sequence privileges are revoked; future migrations must grant explicitly.
6. **Treat service-role access as trusted server access, not tenant isolation.** Supabase `service_role` bypasses RLS. Tenant-qualified authorization in the application remains mandatory for every operation.
7. **Keep the pre-production release candidate on its tested branch.** No production hostname, customer credentials/data, payment flow, paid service, or commercial launch is enabled.

## Target architecture

- **Web:** existing Vercel Hobby static viewer; only approved public configuration reaches the browser.
- **API:** request-scoped Python adapter for bounded intake/status operations, using verified identity claims and tenant-scoped runtime resolution.
- **Execution:** isolated worker execution with immutable worker image digests and resource/network limits. Long jobs use accepted-job/status/download semantics, not a request-bound worker.
- **State:** private `foundry` schema stores bounded job state, idempotency, events and artifact metadata. Large objects remain outside Postgres. No object-storage provider has yet been selected or authorized.
- **Identity:** short-lived/revocable credentials, server-side validation, trusted tenant/actor claims, least-privilege service credentials, and explicit tenant lifecycle.
- **Operations:** correlation IDs, redacted logs, rate limits, admission control, deadlines, health/readiness, alerting and recovery.

## Free-tier and commercial boundary

Vercel Hobby is intended for personal, non-commercial use. It is suitable for pre-revenue development and static preview, not the assumed plan for paid customer service. Verify then-current terms and move to an appropriately licensed plan/provider before commercial launch.

Supabase Free has database, availability and backup limitations. The current database foundation is a pre-production metadata store, not production-grade artifact storage or an always-on service.

## Release gates before a real customer pilot

- [ ] Implement/test request-scoped API adapter for bounded intake/status.
- [ ] Implement asynchronous submission, idempotency, status and download contract.
- [x] Create isolated Foundry schema and verify schema grants.
- [x] Create jobs/events/artifacts tables with RLS and explicit least-privilege grants.
- [x] Revoke default table/sequence grants; explicitly grant the event identity sequence only.
- [ ] Verify `foundry` is absent from Supabase API-exposed schemas and test client-role denial through the API.
- [ ] Implement Python/Postgres repository, canonical hashing, atomic claims, lease fencing and retry behavior.
- [ ] Select and test external object storage, tenant authorization, checksum, retention, deletion and backup/restore.
- [ ] Choose worker hosting based on measured runtime/native dependencies/network/cost; no paid service without approval.
- [ ] Integrate production authentication, credential revocation/rotation and server-side secret injection.
- [ ] Test cross-tenant denial, failure recovery and deployed end-to-end browser submission with artifact checksum.
- [ ] Review commercial plan terms before accepting payment or serving paid customers.

## Consequences

The isolated metadata foundation is provisioned in the existing project without changing Panda Roam's public transit model or creating another paid resource. The job tables are real and permission-hardened, but there is not yet a hosted customer API, worker, object store, or production tenant service. This remains a pre-production engineering branch, not a customer-ready deployment.
