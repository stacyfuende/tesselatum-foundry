# ADR-067: End-to-end authenticated customer product submission

**Status:** Proposed  
**Date:** 2026-11-28

## Context

The authenticated `POST /v1/products` adapter and the process-local tenant
runtime resolver were previously tested separately. That left an important
gap: no test proved that an actual HTTP submission could cross the trusted
authentication boundary, resolve the tenant's installed runtime, execute a
registered spatial capability, pass product acceptance, and return the
verified customer bundle.

## Decision

Add a Docker-backed integration test that exercises the complete path over
real loopback HTTP:

1. Authenticate a bearer token into trusted actor and tenant claims.
2. Decode a bounded GeoJSON source submission.
3. Resolve the tenant's isolated `LocalFoundry` runtime.
4. Resolve the approved Nairobi site-coordinate product template.
5. Ingest the source as an immutable Artifact.
6. Execute the registered `vector.reproject@1.0.0` Docker worker.
7. Evaluate required acceptance checks and assemble the fingerprinted
   product manifest.
8. Return the verified ZIP product bundle over HTTP.

The test also verifies preserved feature identity and properties, plausible
EPSG:32737 Nairobi coordinates, request correlation, and separation between
two tenant runtime instances.

## Verification boundary

The test is opt-in when the CI worker image is configured and uses the
existing isolated Docker worker. It demonstrates the integrated local
development path; it does not establish production hosting, TLS, production
identity-provider integration, distributed tenant provisioning, object-store
IAM, rate limiting, or operational monitoring. Those remain deployment
responsibilities and are not implied by this test.
