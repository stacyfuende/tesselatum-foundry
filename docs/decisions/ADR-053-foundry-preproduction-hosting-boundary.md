# ADR-053 — Foundry pre-production hosting boundary

**Status:** Accepted for the pre-production phase; amended 2026-11-28 with user approval to reuse existing Hobby and Supabase resources  
**Date:** 2026-11-28  
**Scope:** Customer web surface, API runtime, execution workers, durable state

## Context

Foundry's customer API is currently implemented as a standard-library `ThreadingHTTPServer`. Its authentication and tenant runtime are injected by the host, and its successful response is a synchronous ZIP bundle. The execution path can invoke spatial workers and native dependencies. The current local tenant resolver and filesystem stores are development adapters, not shared production infrastructure.

The repository already has a Vercel-linked project named `foundry-product-viewer` connected to this Git repository. The Vercel team is on Hobby. The preview deployment for branch head `796b60b1a7b9cf86041a636ecf60c417174cc20b` is READY; it is the static viewer preview, not a deployed customer API or worker.

The connected Supabase account has two existing projects:
- `tessellatum-core` is active and contains Tessellatum business and Intelligence data, 46 public tables, and two existing Storage buckets. Its application tables have RLS enabled. A `private` schema already exists, but its current grants are not suitable as an assumed Foundry service boundary.
- `panda-roam` is currently inactive and could not be inspected.

The user has authorized continuing with the existing Vercel Hobby plan and investigating reuse of existing Supabase projects. No new paid service or project is authorized or required for this pre-production step.

## Decisions

1. **Keep the customer viewer on Vercel Hobby as a static web surface.** Use preview deployments and the existing project. Do not mistake a READY viewer deployment for a deployed API or worker.
2. **Do not deploy the current threaded HTTP server directly as a Vercel Function.** It owns a listening socket and process-local runtime assumptions; a request-scoped adapter is required.
3. **Use Vercel Hobby for pre-production and bounded control-plane experiments only.** Hobby Functions have a maximum execution duration of 300 seconds. Do not run long spatial jobs, native-heavy raster processing, or durable background workers inside a Hobby Function. Any Function adapter must be request-scoped, bounded, and tested against the plan limits. Heavy execution remains outside the Vercel request lifecycle until an appropriately bounded worker host is selected. Hobby is not the assumed plan for a paid customer-facing service.
4. **Reuse the active `tessellatum-core` project through a dedicated, non-exposed Foundry schema** for bounded job and artifact metadata, subject to a migration that explicitly revokes client access, grants only the server-side service role, enables RLS as defense in depth, and enforces tenant ownership in the application. Do not add Foundry objects to `public`, repurpose Tessellatum Intelligence/business tables, or reuse the existing Storage buckets. Store metadata and references/checksums only; do not store large raster/source files in Postgres. No schema or data writes have been made by this ADR.
5. **Do not use the inactive `panda-roam` project as a runtime dependency** until it is accessible and its ownership/data boundary is deliberately assessed.
6. **Keep the pre-production release candidate on its tested branch.** No production hostname, customer credentials, customer data, payment flow, paid service, or commercial launch is enabled by this ADR.

## Target architecture for the next implementation phase

- **Web:** existing Vercel Hobby static viewer; only public configuration (approved API URL and exact allowed origin) may reach the browser.
- **API:** a separately testable request-scoped Python adapter for lightweight intake/status operations. The host must provide verified identity claims and tenant-scoped runtime resolution. Do not deploy the listening server as a Function.
- **Execution:** bounded, isolated worker execution with immutable worker image digests and resource/network limits. Jobs that outlive an HTTP request use an accepted-job/status/download contract. Vercel Hobby Functions do not act as durable workers.
- **State:** the proposed non-exposed Foundry schema in `tessellatum-core` stores job state, idempotency, status transitions, and artifact metadata only. Large source/output objects remain outside Postgres. Storage lifecycle, checksums, retention, deletion and backup/restore must be designed before customer data is accepted.
- **Identity:** short-lived/revocable credentials, server-side validation, trusted actor and tenant claims, least-privilege service credentials, and explicit tenant provisioning/suspension/deletion.
- **Operations:** request correlation, redacted logs, rate limits, admission control, execution deadlines, health/readiness checks, alerting and recovery procedures.

## Free-tier and commercial-use boundary

The Vercel Hobby plan is documented for personal, non-commercial use. It is suitable for pre-revenue development and static preview, not as the assumed plan for a paid customer-facing service. Before commercial launch, verify the then-current terms and move to an appropriately licensed plan or hosting provider.

Vercel documents a 300-second maximum Function duration on Hobby. Its Python Functions also have packaging and runtime constraints; the current Foundry execution stack must be measured and tested against any proposed serverless packaging before adoption.

Supabase Free currently includes a 500 MB database per project and can pause projects after a week of inactivity; it does not include automatic backups. These constraints make the database suitable for bounded pre-production metadata, not a claim of production-grade artifact storage or always-on customer service.

## Release gates before a real customer pilot

- [ ] Implement and test the request-scoped API adapter for bounded intake/status operations.
- [ ] Define and implement the asynchronous job, idempotency, status and download contract.
- [ ] Add the Foundry-only schema and migration in `tessellatum-core`; verify schema grants, RLS, tenant isolation and advisors before any customer data is accepted.
- [ ] Keep source rasters and large product objects outside Postgres; select a bounded object-storage lifecycle and verify checksums.
- [ ] Choose worker hosting based on measured runtime, native dependency, network egress and cost requirements; no paid service without explicit approval.
- [ ] Integrate production authentication, credential revocation/rotation and server-side secret injection.
- [ ] Enforce per-tenant storage authorization, rate limits, admission control and worker resource limits.
- [ ] Test backup/restore, deletion/retention, failure recovery and deployed cross-tenant denial.
- [ ] Run a deployed end-to-end browser submission and verify the returned Artifact/ZIP checksum.
- [ ] Review commercial plan terms before accepting payment or serving paid customers.

## Consequences

This decision uses the existing free-tier estate without creating another project or silently placing Foundry data in unrelated public tables. It gives Foundry a path to implement a real asynchronous control plane on the existing Supabase account while keeping heavy spatial execution outside Vercel Hobby's request lifecycle. It preserves the distinction between a tested pre-production product factory and a hosted commercial service.
