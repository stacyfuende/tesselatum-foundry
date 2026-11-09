# Launch plan and release gates

**Current target:** a controlled, single-tenant private preview. A public multi-tenant launch is not yet authorized by the current architecture or verification evidence.

This plan distinguishes a runnable demonstration from a release. Do not change a status to “ready” merely because code or a container image exists.

## What exists on the isolated build branch

- Canonical versioned Capability, Cell, Recipe, Artifact, Run, and Validation Report contracts and registries.
- Vector buffer and reprojection implementations with conformance-gated workers and independent output validation.
- Sequential Recipe execution and immutable filesystem-backed local stores.
- A local Python SDK and `foundry` operator CLI.
- A synthetic end-to-end vector-buffer quickstart.
- An optional bearer-authenticated FastAPI control plane and dependency-free Python client.
- A static same-origin browser Console for Artifact intake, JSON definition registration, Recipe execution, Run/report inspection, and checksum-verified output downloads.
- Non-root container build definitions and private deployment guidance.

These components are on an isolated working branch. They have not yet passed the required project test suite, Ruff, Docker builds, or end-to-end deployment verification. The branch is currently 226 commits ahead of and 16 commits behind main, so a clean integration change set and reconciliation of main's newer CI/README/status/vision updates are required before a release PR. The raster Capability remains unintegrated with the Run/Artifact/Recipe lifecycle and its implementation manifest remains `not_run`.

## Gate A — verify the private-preview vertical slice

Complete in this order:

1. Run `python -m pip install -r requirements-dev.txt` in a controlled local environment.
2. Run targeted schema, SDK, CLI, quickstart, API, client, console, worker, and vector execution tests.
3. Run Ruff over the complete changed Python source and tests; correct all findings without weakening tests.
4. Build the control-plane and console images locally. Build both remote worker images and record immutable image IDs.
5. Run the synthetic quickstart through the Console and through the Python client against a local private deployment. Verify Artifact checksums, Run records, independent Validation Reports, and output downloads.
6. Exercise authentication failures, oversized requests, duplicate immutable definitions, unavailable workers, overload rejection, hard timeouts, and worker-secret isolation.
7. Exercise backup and restore of the persistent control-plane volume.
8. Record actual test/build versions, commands, results, and image digests. Keep unverified implementations at `not_run`.

Only after local verification should one deliberate PR validation run be requested. The existing full CI is expensive (Docker/PostGIS and full pytest). No PR, workflow dispatch, or push to a trigger branch should be used as an informal test loop.

## Gate B — controlled private preview

Required before a real user other than the operator is invited:

- Verify the remote-worker concurrency limit and process-isolated hard timeout ported from PRs #13 and #15 on this branch; reconcile or supersede those open PRs after integration review, then verify both in containers.
- Complete security review of the API, shared-token handling, Nginx proxy, worker network boundaries, resource ceilings, and filesystem permissions.
- Put the control plane and workers behind trusted TLS ingress and private networking; apply rate, connection, and request-body limits.
- Store API and worker secrets in a secret manager, document rotation, and test rotation.
- Enable operational logs/metrics/alerts without recording bearer tokens or sensitive Artifact contents.
- Complete backup/restore and failure-recovery drills.
- Agree a data-use and rights policy. A rights declaration is evidence supplied by a caller, not proof of permission or suitability.
- Restrict preview users to synthetic or explicitly approved datasets. Do not use the service for consequential suitability or regulatory decisions without domain-specific methodology validation.

## Gate C — public multi-tenant launch

The current API and filesystem stores are not a multi-tenant security boundary. A public launch requires separate architectural work:

1. User identity and authentication integration; role-based authorization and organization/project membership.
2. Tenant-scoped resource authorization on every Artifact, Cell, Recipe, Run, and Report operation.
3. Database-backed transactional metadata persistence, migrations, concurrency control, and durable job state.
4. Managed object storage with tenant isolation, encryption, retention, lifecycle policies, and signed/authorized downloads.
5. Bounded scheduling, queueing, quotas, cancellation, retries/resume semantics, and per-tenant resource accounting.
6. Worker pool isolation, hardened execution, supply-chain controls, image signing/scanning, secret rotation, and auditable runtime provenance.
7. Browser UX beyond JSON authoring: visual Recipe graph editing, map/spatial preview, accessibility, and usable validation feedback.
8. Privacy, data-retention, security incident, support, service-level, and billing policies.

## Release discipline

- Keep development on `fix/raster-capability-semantics-schema` until a deliberate integration decision is made.
- Do not push to `main`, feature trigger branches, open PRs, or dispatch Actions without explicit approval.
- Prefer local tests and builds. Never weaken or skip tests to obtain a green result.
- Do not mark Rasterio, remote workers, the API, or Console as production-ready without their corresponding evidence.
- Keep this plan and `docs/PROJECT_STATUS.md` synchronized as gates are actually completed.
