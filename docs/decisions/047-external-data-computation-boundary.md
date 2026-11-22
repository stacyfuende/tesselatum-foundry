# ADR-047: Keep external spatial data external; Foundry owns computation

- **Status:** Accepted
- **Date:** 2026-11-22
- **Supersedes:** ADR-045 and ADR-046

## Context

Foundry's trajectory is a reusable spatial computation platform built around Capabilities, Implementations, Geo-Cells, Recipes, Runs, Artifacts, workers and independent validation.

The proposed persistent geographic entity database and bulk source-data storage plane changed the product into a data warehouse and ingestion/reconciliation platform. That introduces substantial responsibilities—custody, retention, licensing, access control, backups, data freshness, global scale and operational cost—that are not necessary to deliver Foundry's core value.

Spatial data is already distributed across providers, customer databases, object stores, APIs and local environments. A central copy is often wasteful, stale, legally constrained or too large. Foundry should make those sources computable without requiring ownership of their contents.

## Decision

Foundry is a **spatial computation and orchestration platform**, not a universal spatial data repository.

1. Source datasets remain with their provider, customer or chosen storage system by default.
2. Foundry accesses external sources through explicit adapters and references.
3. Adapters expose metadata and bounded reads (windows, streams, pagination, query pushdown) rather than requiring whole-dataset ingestion.
4. Computation contracts remain independent of source providers and storage engines.
5. Run provenance records source identity, locator/reference, query/filter parameters, version/ETag/checksum evidence where available, retrieval time, schema/CRS metadata and reproducibility limitations.
6. Credentials are injected at runtime through scoped mechanisms. They are never embedded in Cell/Recipe definitions or persisted in Run logs.
7. Foundry may persist immutable definitions, Run events, validation reports, bounded cache entries and derived output Artifacts under explicit retention and access policies.
8. Customers may choose to retain input snapshots in their own storage. Foundry does not silently mirror or archive entire upstream datasets.
9. Cache reuse is permitted only when source evidence and all other cache-relevant inputs satisfy the declared reproducibility policy. Mutable/unversioned sources must be treated as such.

## Consequences

- The proposed geographic entity/PostGIS information schema, repositories and bulk source ingestion pipeline are not part of Foundry's core and are removed from the active implementation.
- The object-storage uploader built specifically for source snapshot ingestion is removed. A future artifact backend may use object storage for derived outputs without becoming a source-data warehouse.
- Existing Artifact, Capability, Geo-Cell, Recipe, Run, worker, validation and SDK contracts remain the computational foundation.
- The next data-plane work is a small external source protocol, bounded reader adapters and Run provenance—not a data lake or ingestion service.
- Source availability and mutability become explicit execution concerns. Reproducibility is limited by the evidence each provider exposes.
- Storage cost is not eliminated: derived outputs, caches and execution evidence still require deliberate retention and lifecycle policies.

## Alternatives considered

### Foundry-owned spatial database and ingestion platform

Rejected as the default direction. It would duplicate upstream custody and turn Foundry into a large data operations business before the computation platform is complete.

### Copy every input to immutable object storage

Rejected as a mandatory policy. It can improve reproducibility for selected workflows, but increases storage, transfer, legal and retention obligations. Customer-controlled snapshots remain an option.

### No persistence at all

Rejected. Definitions, Runs, validation evidence and derived Artifacts are essential to reproducible computation. The decision is to scope persistence to computation, not eliminate it.

## Implementation sequence

1. Remove the proposed information database, source ingestion schema and source snapshot uploader from active Foundry code.
2. Preserve the established computation contracts and their existing PostGIS conformance tests.
3. Define a minimal external data reference and source adapter contract.
4. Implement a local-file adapter with bounded iteration and explicit metadata.
5. Carry source references and available version evidence into Run provenance and cache decisions.
6. Extend to customer/provider connectors only when a real workflow requires them.
