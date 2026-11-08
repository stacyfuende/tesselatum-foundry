# ADR-034: Shared spatial worker identity with capability-specific execution contracts

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry now has two independently implemented vector operations with distinct request semantics: `vector.buffer` requires a projected measurement CRS, while `vector.reproject` requires an explicit target CRS. Both workers nevertheless expose the same operational identity: worker ID/type, exact capability and implementation versions, and an immutable runtime image digest. Both return the same untrusted result envelope containing a FeatureCollection, CRS declaration, duration, and runtime image digest.

ADR-019 deliberately deferred a generic worker protocol until a second real operation demonstrated which concepts were actually common.

## Decision

1. Extract only the proven common identity and runtime-digest surface into `SpatialWorkerIdentity`.
2. Keep operation request/execute signatures capability-specific. `VectorBufferWorker` and `VectorReprojectWorker` extend the shared identity protocol but retain distinct typed parameters.
3. Keep `WorkerResult` as a shared untrusted transport envelope. The control plane remains responsible for validating output CRS, geometry, metadata, dimensionality, and provenance before Artifact registration.
4. Keep Recipe orchestration capability-agnostic. It resolves the exact capability-version runner; each Run service validates and invokes its own capability-specific worker protocol.
5. Do not introduce arbitrary payload dispatch, a general plugin loader, worker discovery, or automatic cross-capability fallback. Add those only when another concrete operation demonstrates a stable need.

## Consequences

- Recipe runner configuration can reason about worker identity without assuming operation-specific request parameters.
- Capability-specific Run services retain static, explicit execution contracts.
- The common result envelope is reused without weakening the independent output critic.
- New capabilities must provide their own semantic preflight, worker request, output critic, and conformance suite.

## Alternatives considered

- **Keep all worker metadata duplicated per protocol:** rejected because two independent operations now prove these fields are common.
- **Use one generic `execute(payload: dict)` method:** rejected because it would erase operation-specific parameter types and move errors to runtime.
- **Create a universal plugin/worker framework now:** deferred as premature abstraction.
