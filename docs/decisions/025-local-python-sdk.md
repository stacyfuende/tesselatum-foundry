# ADR-025: Provide a small local Python SDK composition root

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry now has separate local adapters for Artifact storage, immutable Cell/Recipe definitions, Run persistence, canonical Capability and implementation registries, a single-cell Run service, and sequential Recipe execution. Consumers currently need to understand and assemble those internal components themselves. That creates an unnecessary integration burden and risks inconsistent wiring of shared contract registries and stores.

ADR-003 establishes the API/SDK and serialized contracts as canonical. The first SDK surface should make the already-proven local workflow accessible without introducing a network server, a second workflow representation, or a new domain object.

## Decision

1. Expose a `LocalFoundry` composition root from the top-level Python package.
2. Require an explicit persistent root directory. Store Artifacts, Run records, and immutable definitions in separate subdirectories beneath it.
3. Construct one shared ContractRegistry and inject it into the local stores and registries.
4. Expose concise operations to register exact Cell and Recipe versions, execute an exact registered Recipe version, retrieve Runs, list Runs correlated to a Recipe execution, and retrieve/read checksum-verified Artifacts.
5. Permit injection of a worker adapter for tests and controlled local integrations; default to the isolated Docker Shapely worker.
6. Keep the facade explicitly local. It is not a network API, authentication boundary, tenant boundary, distributed scheduler, or production multi-instance service.
7. Keep the underlying stores and services accessible as named attributes for advanced SDK consumers, while treating the facade methods as the stable convenience surface.

## Consequences

A Python consumer can use the canonical contracts and execution path without manually assembling the control plane. Local storage remains explicit and inspectable. The same domain services can later be composed behind an authenticated API without changing the serialized domain contracts.

The first SDK surface is intentionally narrow and does not promise remote workers, generic capability dispatch, parallel scheduling, or server-side identity management.

## Alternatives considered

- **Expose only low-level stores and services:** rejected as the sole entrypoint because every consumer would need to recreate the same dependency wiring.
- **Build a network API server now:** deferred until the local API/SDK boundary and execution lifecycle are proven.
- **Make the SDK maintain a second recipe/workflow model:** rejected because serialized contracts remain canonical.
