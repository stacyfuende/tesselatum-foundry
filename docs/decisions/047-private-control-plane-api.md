# ADR-047: Add a private authenticated single-tenant control-plane API

- **Status:** Accepted for private preview; production deployment not approved
- **Date:** 2026-11-09

## Context

The local SDK and operator CLI provide reproducible workflows, but integrations need a network boundary for Artifact transfer, immutable definition registration, Recipe execution, and inspection of Runs and Validation Reports.

The existing remote workers already provide a replaceable execution boundary. The first API can therefore use those workers without mounting the Docker socket into the control-plane container.

## Decision

1. Add an optional FastAPI control plane with bearer-token authentication and a minimum 32-character API token.
2. Expose authenticated endpoints for canonical Capability/implementation discovery, Artifact ingest/read/export, Cell and Recipe registration/read, Recipe execution, Run listing/inspection, and Validation Report inspection.
3. Require JSON request bodies with an explicit Content-Length and enforce a configurable request-size ceiling. Artifact content is base64 encoded within that bounded JSON request.
4. Disable interactive API documentation; set no-store, nosniff, and no-referrer response headers; compare bearer credentials in constant time.
5. Keep the control plane single-tenant and backed by the existing local filesystem stores. Deploy one Uvicorn worker against one persistent volume. Use HTTPS remote workers so the control plane does not need a Docker socket.
6. Run the control-plane container as non-root with a read-only root filesystem, dropped capabilities, process/memory/CPU limits, and a writable persistent data volume.
7. Require a trusted TLS ingress, private worker networking, ingress rate/body/connection limits, secret management, backup/restore, and monitoring outside the application.
8. Do not describe this API as multi-tenant or production-hardened. User identities, roles, tenant isolation, database-backed persistence, per-tenant quotas/encryption, and production worker hardening remain separate launch requirements.

## Consequences

- External clients can use the same canonical Artifact, Cell, Recipe, Run, and Validation Report model as the local SDK.
- Worker execution remains outside the control-plane container; remote worker image identity is still checked by the existing adapter.
- The current filesystem stores and process-local locking constrain deployment to one control-plane process and one tenant.
- The shared bearer token is an integration credential, not a user identity or authorization system.
- API write requests are bounded, but ingress rate limiting and remote-worker concurrency/timeouts remain necessary.
- A dependency-free Python client provides safe URL handling, redirect rejection, bounded transport, and SHA-256 verification for downloaded Artifact bytes.

## Verification status

The API factory, optional dependencies, authentication and request-size checks, API tests, non-root container image, environment template, and private deployment guide are committed on the isolated branch. The API tests have not been executed, the container has not been built, and no end-to-end remote-worker deployment has been exercised. The worker concurrency and process-isolated timeout implementations from PRs #13 and #15 are now ported onto the isolated branch; container-level verification remains a release gate. This ADR authorizes implementation and controlled private-preview evaluation only.
