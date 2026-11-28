# Customer Product API — Deployment and Operations Guide

**Status:** Deployment specification; no production host is configured.  
**Current endpoint contract:** `POST /v1/products`  
**First supported product:** Nairobi site-coordinate standardization from a WGS 84 GeoJSON Point FeatureCollection.

This guide defines the boundary between the tested customer submission flow and a real hosted service. It is deliberately provider-neutral: the repository does not yet contain production credentials, a production identity provider, a durable tenant store, or an approved API hostname.

## What is already implemented

- A browser request composer that inspects GeoJSON locally and requires an explicit submit confirmation.
- A customer API that accepts a versioned JSON envelope and source file bytes, authenticates before resolving a tenant runtime, and never trusts tenant or actor IDs from the request body.
- Exact-origin CORS configuration, HTTPS-only remote origins, bounded request/source sizes, and sanitized caller-facing errors.
- A local tenant runtime reference implementation with separate per-tenant local stores.
- A tested end-to-end loopback HTTP integration path through the registered reproject worker, product acceptance, and ZIP delivery.
- CI evidence: commit `053e69737b58096351cd01209aae72f50099e297` passed 562 tests; two optional live-STAC tests were skipped because their separate environment was not configured. The independent live Nairobi Sentinel-2 raster workflow also passed.

These results establish the local product path. They do not establish a public production service.

## Required deployment shape

Use two independently deployable surfaces:

1. **Customer web page:** static hosting is suitable. Configure the operator-issued API URL in the page at submission time. Do not embed a shared service credential in HTML or JavaScript.
2. **Customer API and execution service:** a long-running container/service or a serverless-compatible HTTP adapter. The current `create_customer_product_server` returns a standard-library `ThreadingHTTPServer`; do not invoke it as though it were a request-scoped serverless handler. A serverless deployment needs an explicit adapter that preserves the same auth, tenant, request-size, CORS and response contracts.

The API service must sit behind a trusted HTTPS ingress. The ingress is responsible for controls that the small HTTP adapter intentionally does not pretend to provide.

## Identity and tenant boundary

The hosting application must provide two trusted functions:

- `authenticate(authorization_header)`: validate a short-lived or revocable bearer credential with the chosen identity provider and return non-empty `actor_id` and `tenant_id` claims, or reject it.
- `resolve_tenant_runtime(tenant_id)`: return the approved execution services and tenant-scoped storage for that authenticated tenant.

Never derive tenant identity from request JSON, query parameters, a caller-supplied path, or an unverified header. Do not accept customer-supplied capabilities, worker images, recipes, templates, storage paths, or execution policy.

Before real customer data is accepted, tenant isolation must be enforced by storage IAM/authorization and service boundaries—not merely by hashed directories or separate Python objects. Test cross-tenant reads, writes, artifact retrieval and request correlation. Define tenant provisioning, suspension, deletion, retention and backup procedures.

## Network and ingress controls

Configure all of the following before exposing the API:

- TLS at the ingress; redirect or reject plaintext remote traffic.
- A strict request-body limit no greater than the adapter's configured 36 MiB envelope limit, and a source-file limit no greater than 25 MiB.
- Request/header timeouts, bounded concurrent requests, per-tenant and per-credential rate limits, and an execution deadline.
- A queue or admission-control policy so simultaneous customer requests cannot exhaust memory, CPU, worker capacity or storage.
- Exact browser-origin allowlisting through `allowed_origins`; do not use wildcard CORS. CORS is a browser policy, not authentication.
- No redirects on authenticated API requests. Preserve `Cache-Control: no-store` for submissions and product responses.
- Egress controls for any external spatial data adapters; do not permit arbitrary customer-selected network fetches.
- A health/readiness check that does not expose tenant data, credentials or internal paths.

The browser must use the operator-approved HTTPS URL and bearer credential. Credentials must be scoped, revocable and rotated. Never put secrets in the static site, repository, deployment logs or customer request JSON.

## Durable storage and execution

The current `LocalTenantRuntimeResolver` is a single-host development adapter. Before multi-instance production:

- Replace local filesystem tenant stores with a durable backend that supports per-tenant authorization, encryption, backup and retention.
- Ensure Artifact publication is atomic and that object access is tenant-scoped. Keep immutable Artifact identity, checksums, Run lineage and acceptance evidence.
- Pin worker images by immutable digest and run them with least privilege, bounded CPU/memory/disk, network policy and hard execution deadlines.
- Make retries idempotent at the request/product level; prevent duplicate billing or duplicate customer delivery.
- Define artifact expiration, customer download expiry, deletion requests and incident recovery.
- Decide whether the initial synchronous ZIP response is sufficient. If execution can exceed ingress/client timeouts, move to an asynchronous job/status/download contract rather than increasing timeouts indefinitely.

Do not claim a product is delivered until the acceptance gate passes and the exact bundle checksum is verified.

## Observability and incident response

Add structured, redacted operational telemetry outside the request payload:

- correlation/request ID, tenant-safe pseudonymous identifier, actor-safe identifier, start/end time and terminal status;
- queue wait, execution duration, bytes accepted, worker image digest, Artifact IDs/checksums and acceptance outcome;
- counts for authentication failures, rate limits, rejected inputs, worker failures and release denials.

Never log bearer tokens, source contents, raw authorization headers or sensitive customer properties. Retain enough diagnostic evidence to investigate a failed Run without exposing internal traces to customers. Define alert thresholds, on-call ownership, backup restoration and credential-revocation procedures before launch.

## Release gates

A production launch is blocked until every item below is evidenced:

- [ ] Production API hostname and TLS certificate are active.
- [ ] Identity provider, credential issuance/revocation/rotation and trusted actor/tenant claims are integrated.
- [ ] Durable tenant-scoped Artifact/Run/definition storage is configured and cross-tenant isolation tests pass.
- [ ] Ingress body/time/concurrency limits, rate limits and execution deadlines are active.
- [ ] Exact customer web origin is configured in API CORS.
- [ ] Worker image digests, resource limits, network policy and execution isolation are pinned.
- [ ] Retention, deletion, backup and restore procedures are tested.
- [ ] Redacted logs, metrics, alerts and incident ownership are in place.
- [ ] A real browser submission from the deployed customer page returns a verified ZIP for an authorized test tenant.
- [ ] Negative tests prove unauthorized, cross-tenant, oversized, disallowed-origin and non-releasable requests cannot obtain a product.

## Current deployment blocker

No production hostname, identity-provider integration, tenant storage backend, or deployment credentials have been supplied or configured. The Vercel team currently hosts the static viewer projects on the Hobby plan; its recent preview builds reported a build-rate limit. Vercel preview availability is not a substitute for an API runtime or production readiness.

The next deployment decision is therefore a hosting/identity/storage choice, followed by a real authorized browser-to-API test. Until those dependencies exist, keep the API private and the customer page in pilot mode.


## Pre-production certification before cloud provisioning

Do not provision the production host merely to discover software defects or incomplete customer workflows. Use the repository's [Pre-Production Certification](preproduction-certification.md) process first.

Run `python scripts/preproduction_certify.py --profile local` for the no-cloud local gates. CI runs the same suite with Docker worker images and PostGIS through `--profile ci`. The generated JSON report records the profile, commit, individual gate results and known limitations.

A green local/CI report is not a substitute for hosted acceptance. Browser automation, production identity integration, cloud IAM, durable object-storage isolation, restore testing, ingress controls and cost measurements remain explicit release gates. Provision Google Cloud only after those customer and operational gates have evidence.
