# ADR-066: Local tenant runtime isolation for customer product execution

- **Status:** Proposed
- **Date:** 2026-11-28
- **Decision area:** Customer API / runtime composition

## Context

The authenticated `POST /v1/products` adapter already derives actor and tenant
identity from the authentication callback and delegates runtime lookup to a
host-supplied resolver. Until now, the repository had no concrete resolver.
That left storage and execution isolation as an obligation with no reference
implementation.

## Decision

Add `LocalTenantRuntimeResolver` as a concrete single-host composition adapter.
It creates one `LocalFoundry` instance per authenticated tenant, rooted in a
directory derived from SHA-256(tenant ID), and caches that instance for the
process lifetime. Consequently each tenant receives separate filesystem
Artifact, Run and immutable-definition stores, CapabilityRegistry and Recipe
Execution Service instances.

The resolver supplies only the reviewed `vector.reproject@1.0.0` Cell template
and output mapping for the installed Nairobi site-coordinate-standardization
job. It does not accept templates, capabilities, worker images, storage paths
or execution configuration from customer input.

The tenant identifier must come from the API's trusted authentication result.
It is never accepted from the request body and is never used directly as a
filesystem path.

## Consequences and limits

- This closes the missing local runtime-composition gap and supports an
  end-to-end authenticated API integration when a worker image is available.
- Runtime caching and filesystem roots are process-local/single-host. Multiple
  hosts require a shared storage backend with tenant-scoped authorization,
  durable provisioning, and distributed coordination.
- Filesystem directory separation is not a substitute for OS/container
  isolation, encryption at rest, backup/retention controls, or a production
  object-store IAM policy.
- Authentication, TLS termination, session lifecycle, rate limiting,
  concurrency limits, request deadlines, secret rotation and operational
  monitoring remain hosting responsibilities.
- The resolver does not itself authenticate a user or create a public service.

## Verification

Unit tests verify stable runtime reuse for one tenant, distinct stores and
runtime objects across tenants, hashed path isolation, approved job bindings,
and rejection of empty or malformed tenant identifiers.
