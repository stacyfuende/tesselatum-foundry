# ADR-053 — Foundry pre-production hosting boundary

**Status:** Accepted for the pre-production phase  
**Date:** 2026-11-28  
**Scope:** Customer web surface, API runtime, execution workers, durable state

## Context

Foundry's customer API is currently implemented as a standard-library `ThreadingHTTPServer`. Its authentication and tenant runtime are injected by the host, and its successful response is a synchronous ZIP bundle. The execution path can invoke spatial workers and native dependencies. The current local tenant resolver and filesystem stores are development adapters, not shared production infrastructure.

The repository already has a Vercel-linked project named `foundry-product-viewer` connected to this Git repository. That project is a customer-facing viewer surface; its existence does not mean the API or worker runtime is deployed. The Vercel team is currently on Hobby.

The connected Supabase account has a shared project named `tessellatum-core` with existing Tessellatum business and Intelligence data. It is not a dedicated Foundry database. The existing project must not be silently repurposed for Foundry execution state or customer artifacts.

## Decision

1. **Keep the customer viewer on Vercel as a static web surface.** Do not treat the existing viewer project as a deployed Foundry API.
2. **Do not deploy the current threaded HTTP server directly as a Vercel Function.** It owns a listening socket and process-local runtime assumptions; a request-scoped Function needs a distinct adapter.
3. **Do not attempt production customer execution on Vercel Hobby in this phase.** Hobby Functions have a maximum execution duration of 300 seconds, and the current product path has no asynchronous job/status/download contract or durable shared worker coordination. A Function wrapper alone would not solve those constraints.
4. **Do not add Foundry tables or artifacts to the shared `tessellatum-core` Supabase project yet.** First define the Foundry persistence boundary and verify isolation, storage lifecycle, and resource budgets. No existing Tessellatum Intelligence or business tables are to be repurposed.
5. **Keep the pre-production release candidate on its tested branch.** No production hostname, credentials, paid service, customer data, or payment flow is enabled by this ADR.

## Target architecture for the next implementation phase

- **Web:** existing Vercel static viewer project; only public configuration (approved API URL and exact allowed origin) may reach the browser.
- **API:** a separately deployable Python HTTP application with a request-scoped ASGI/WSGI adapter or a long-running container host. The host must provide verified identity claims and tenant-scoped runtime resolution.
- **Execution:** bounded, isolated worker execution with immutable worker image digests and resource/network limits. If jobs can exceed request deadlines, use an asynchronous accepted-job/status/download contract rather than holding an HTTP request open.
- **State:** durable tenant-scoped metadata and object storage with atomic publication, checksums, retention, deletion and backup/restore procedures. Process memory and local filesystem are not authoritative shared state.
- **Identity:** short-lived/revocable credentials, server-side validation, trusted actor and tenant claims, least-privilege service credentials, and explicit tenant provisioning/suspension/deletion.
- **Operations:** request correlation, redacted logs, rate limits, admission control, execution deadlines, health/readiness checks, alerting and recovery procedures.

## Free-tier and commercial-use boundary

The Vercel Hobby plan is documented for personal, non-commercial use. It is suitable for this project's pre-revenue development and static preview, not as the assumed plan for a paid customer-facing service. Before commercial launch, verify the then-current terms and move to an appropriately licensed plan or hosting provider.

Vercel documents a 300-second maximum Function duration on Hobby. Its Python Functions also have packaging and runtime constraints; the current Foundry execution stack must be measured and tested against any proposed serverless packaging before adoption.

Supabase Free currently includes a 500 MB database per project and can pause projects after a week of inactivity; it does not include automatic backups. Those constraints are not a suitable basis for claiming durable production artifact storage or an always-on customer service.

## Release gates before a real customer pilot

- [ ] Choose the API/worker host based on measured runtime, native dependency, network egress and cost requirements.
- [ ] Implement and test a request-scoped API adapter, or choose a container host that can run the existing server safely behind trusted ingress.
- [ ] Define the async job contract if execution may exceed the synchronous request budget.
- [ ] Select a dedicated or explicitly partitioned durable Foundry persistence backend; document data ownership and tenant isolation.
- [ ] Integrate production authentication, credential revocation/rotation and server-side secret injection.
- [ ] Enforce per-tenant storage authorization, rate limits, admission control and worker resource limits.
- [ ] Test backup/restore, deletion/retention, failure recovery and deployed cross-tenant denial.
- [ ] Run a deployed end-to-end browser submission and verify the returned Artifact/ZIP checksum.
- [ ] Review commercial plan terms and obtain explicit approval for any recurring or usage-based spend.

## Consequences

This decision deliberately separates a working pre-production spatial product factory from a hosted commercial service. It preserves the passing release candidate and current free-tier estate without creating hidden spend or placing Foundry's data into unrelated shared systems. It also avoids a misleading deployment in which a static viewer is mistaken for an operational API.
