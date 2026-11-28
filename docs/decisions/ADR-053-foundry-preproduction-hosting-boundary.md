# ADR-053 — Foundry pre-production hosting boundary

**Status:** Accepted for the pre-production phase; amended 2026-11-28 after inspection and user approval to reuse existing Hobby and Supabase resources  
**Date:** 2026-11-28  
**Scope:** Customer web surface, API runtime, execution workers, durable state

## Context

Foundry's customer API is currently implemented as a standard-library `ThreadingHTTPServer`. Its authentication and tenant runtime are injected by the host, and its successful response is a synchronous ZIP bundle. The execution path can invoke spatial workers and native dependencies. The current local tenant resolver and filesystem stores are development adapters, not shared production infrastructure.

The repository already has a Vercel-linked project named `foundry-product-viewer` connected to this Git repository. Its READY preview deployment is the static viewer only, not a deployed customer API or worker.

The connected Supabase account has two relevant existing projects:
- `tessellatum-core` is active and contains Tessellatum business and Intelligence data. It is not the selected Foundry database because its existing application estate should remain separate.
- `panda-roam` is now active and has an existing spatial-transit model in `public`, including 26 application tables, PostGIS 3.3.7, and existing RLS configuration. Those tables and the rest of the Panda Roam estate are not Foundry resources and must not be altered.

Read-only inspection of Panda Roam found no rows in the application tables, no Storage buckets, and no Edge Functions. The project has existing advisor findings. The public schema and its grants are not an acceptable place for Foundry objects.

The user explicitly directed that Foundry use its own schema and that existing Panda Roam resources must not be disturbed. No new paid service or Supabase project is authorized or required for this pre-production step.

## Decisions

1. **Keep the customer viewer on Vercel Hobby as a static web surface.** Use preview deployments and the existing project. Do not mistake a READY viewer deployment for a deployed customer API or worker.
2. **Do not deploy the current threaded HTTP server directly as a Vercel Function.** It owns a listening socket and process-local runtime assumptions; a request-scoped adapter is required.
3. **Use Vercel Hobby for pre-production and bounded control-plane experiments only.** Hobby Functions have a maximum execution duration of 300 seconds. Do not run long spatial jobs, native-heavy raster processing, or durable background workers inside a Hobby Function. Heavy execution remains outside the Vercel request lifecycle until an appropriately bounded worker host is selected. Hobby is not the assumed plan for a paid customer-facing service.
4. **Use only the dedicated `foundry` schema in the existing `panda-roam` project for Foundry metadata.** The schema has been created and verified. It is owned by `postgres`; `anon` and `authenticated` have neither USAGE nor CREATE; `service_role` has USAGE but not CREATE. No Foundry tables or other schema objects have been created. The migration `supabase/migrations/20261128000100_foundry_private_schema.sql` codifies the isolated schema boundary and default grants. Keep `foundry` out of Supabase's API-exposed schema list. Do not add Foundry objects to `public`, modify existing Panda Roam tables, policies, grants, extensions, buckets, or functions, or reuse Panda Roam data as Foundry data.
5. **Apply least privilege to future metadata objects.** New tables must be created only by controlled migrations, explicitly enable and force RLS where compatible, and have explicit tenant-scoped access policies. The Supabase `service_role` bypasses RLS, so its use is strictly server-side and tenant authorization must be enforced by trusted application code; RLS is not a substitute for that boundary. Do not place service credentials in browser code. Default grants do not automatically enable RLS.
6. **Keep the pre-production release candidate on its tested branch.** No production hostname, customer credentials, customer data, payment flow, paid service, or commercial launch is enabled by this ADR.

## Target architecture for the next implementation phase

- **Web:** existing Vercel Hobby static viewer; only public configuration (approved API URL and exact allowed origin) may reach the browser.
- **API:** a separately testable request-scoped Python adapter for lightweight intake/status operations. The host must provide verified identity claims and tenant-scoped runtime resolution. Do not deploy the listening server as a Function.
- **Execution:** bounded, isolated worker execution with immutable worker image digests and resource/network limits. Jobs that outlive an HTTP request use an accepted-job/status/download contract. Vercel Hobby Functions do not act as durable workers.
- **State:** the non-exposed `foundry` schema in `panda-roam` stores bounded job state, idempotency, status transitions, and artifact metadata only. Large source/output objects remain outside Postgres. Do not use Panda Roam's existing Storage estate; none was found during inspection. Storage lifecycle, checksums, retention, deletion and backup/restore must be designed before customer data is accepted.
- **Identity:** short-lived/revocable credentials, server-side validation, trusted actor and tenant claims, least-privilege service credentials, and explicit tenant provisioning/suspension/deletion.
- **Operations:** request correlation, redacted logs, rate limits, admission control, execution deadlines, health/readiness checks, alerting and recovery procedures.

## Free-tier and commercial-use boundary

The Vercel Hobby plan is documented for personal, non-commercial use. It is suitable for pre-revenue development and static preview, not as the assumed plan for a paid customer-facing service. Before commercial launch, verify the then-current terms and move to an appropriately licensed plan or hosting provider.

Vercel documents a 300-second maximum Function duration on Hobby. Its Python Functions also have packaging and runtime constraints; the current Foundry execution stack must be measured and tested against any proposed serverless packaging before adoption.

Supabase Free has database, availability and backup limitations. The database is suitable for bounded pre-production metadata, not a claim of production-grade artifact storage or always-on customer service.

## Release gates before a real customer pilot

- [ ] Implement and test the request-scoped API adapter for bounded intake/status operations.
- [ ] Define and implement the asynchronous job, idempotency, status and download contract.
- [x] Create the Foundry-only schema in `panda-roam`, verify schema grants, and commit the idempotent migration. No tables have been created yet.
- [ ] Verify `foundry` is absent from the Supabase API-exposed schema list and test client-role denial through the API.
- [ ] Add Foundry metadata tables with explicit RLS, tenant-scoped policies, and migration tests; account for the service role's RLS bypass.
- [ ] Keep source rasters and large product objects outside Postgres; select a bounded object-storage lifecycle and verify checksums.
- [ ] Choose worker hosting based on measured runtime, native dependency, network egress and cost requirements; no paid service without explicit approval.
- [ ] Integrate production authentication, credential revocation/rotation and server-side secret injection.
- [ ] Enforce per-tenant storage authorization, rate limits, admission control and worker resource limits.
- [ ] Test backup/restore, deletion/retention, failure recovery and deployed cross-tenant denial.
- [ ] Run a deployed end-to-end browser submission and verify the returned Artifact/ZIP checksum.
- [ ] Review commercial plan terms before accepting payment or serving paid customers.

## Consequences

This decision reuses the existing spatially enabled Supabase project without creating another project or silently placing Foundry data in Panda Roam's public transit model. The schema boundary is in place, but Foundry has no database tables yet and is not connected to a hosted customer API or worker. The design preserves a clear separation between a tested pre-production product factory and a hosted commercial service.
