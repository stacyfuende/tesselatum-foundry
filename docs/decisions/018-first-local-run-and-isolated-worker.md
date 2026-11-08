# ADR-018: First local Run path and isolated single-cell worker

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry now has two independent, conformance-tested implementations of `vector.buffer@1.0.0`, but a capability that can only be called directly by library code is not yet an execution system. The next proof must connect a declared Geo-Cell to immutable Artifact bytes, a Run lifecycle, an isolated worker, output validation, and a registered output Artifact.

The first execution increment should prove this boundary without prematurely introducing a scheduler, Recipe orchestration, remote workers, arbitrary user code, or a general-purpose plugin runtime.

## Decision

1. Implement the first executable path for one exact Geo-Cell version using the `vector.buffer@1.0.0` capability. It accepts one immutable Artifact input on the `features` port and emits one immutable output Artifact on `result`.
2. Persist Run records in a local JSON-backed control-plane repository. Each Run snapshots the exact Geo-Cell and Capability versions, input Artifact identity and SHA-256 checksum, normalized parameters, attempt number, implementation identity, worker identity/type, and immutable runtime image ID digest.
3. A retry creates a new Run ID and attempt number. It is permitted only when the prior attempt is failed or timed out and explicitly marked retryable. A prior terminal Run remains unchanged.
4. Execute Shapely in a pre-built Docker image pinned by the local immutable image ID, not a mutable image tag. The worker runs as a non-root user with no network, read-only root filesystem, dropped Linux capabilities, no-new-privileges, PID, CPU, memory, wall-clock, temporary-filesystem, input-size, and output-file-size limits.
5. Before creating a Run, the control plane applies the engine-neutral buffer request validator to the exact input bytes and verifies that the Artifact's declared geometry-type set matches the feature data. The worker repeats the same request validation inside the isolated container. The worker receives a versioned JSON request and read-only input file through bind mounts. Its output is staged in a separate writable mount. The host treats all worker output as untrusted and validates its transport shape and actual geometry semantics before registering an Artifact.
6. The independent output critic checks output FeatureCollection structure, feature count, feature IDs and properties, CRS equality with the input and declared output contract, permitted Polygon/MultiPolygon types, non-empty valid geometry, and 2D dimensionality. A failed output produces a failed Run and a persisted Validation Report; it MUST NOT register an output Artifact.
7. A successful output is stored as a new immutable Artifact with checksum, spatial metadata, inherited rights metadata when present, and producer Run provenance. The Run then reaches the succeeded terminal state and references the output Artifact and Validation Report.
8. The local worker protocol is replaceable. The current Docker adapter is not the remote worker implementation and does not establish scheduler, multi-tenant, or distributed-execution semantics.

## Consequences

Foundry now has a narrow end-to-end execution slice that exercises the boundary between declaration, control plane, isolated compute, independent output checking, and immutable storage. The first path is deliberately single-cell and local. It does not yet execute Recipe DAGs, resolve cell-to-cell outputs, schedule multiple workers, execute PostGIS through the same worker interface, cache results, or support remote execution.

The JSON-backed Run repository provides durable local records and serializes updates within one process. It is not a distributed concurrency-control mechanism. The filesystem Artifact store is a local adapter; its file URIs are not portable across hosts. These adapters must be replaced or extended before multi-process or multi-host deployment.

The worker is constrained but is not yet a complete hostile multi-tenant sandbox. Production hardening still requires a threat model, tenant-scoped artifact access, credential policy, host-level disk quotas, worker lifecycle supervision, and deployment-specific isolation review.

## Alternatives considered

- **Start with a general-purpose scheduler:** rejected because it adds orchestration complexity before one execution path is proven.
- **Run Shapely in the control-plane process:** rejected because engine execution must be isolated from control-plane state and dependencies.
- **Trust worker exit status or its output file:** rejected because process success does not prove output contract compliance.
- **Register output before independent validation:** rejected because invalid or malicious worker output must not become a successful Artifact.
- **Treat a Docker image tag as execution identity:** rejected because tags are mutable; the Run records and executes the inspected immutable image ID.
- **Implement remote execution now:** deferred until the local protocol, lifecycle, and output guarantees are exercised end to end.
