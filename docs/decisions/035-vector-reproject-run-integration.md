# ADR-035: Integrate vector.reproject into the immutable Run and Recipe lifecycle

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

ADR-033 established the semantic contract and conformance-tested kernel for `vector.reproject@1.0.0`, while explicitly withholding execution eligibility until an independent output critic and Run service existed. The second capability must participate in Foundry's actual execution model: immutable inputs, exact implementation conformance, isolated workers, Run provenance, validation evidence, immutable output Artifacts, and Recipe lineage.

## Decision

1. Add a capability-specific `VectorReprojectRunService` that uses the same canonical registries, Artifact store, Run repository, worker identity, immutable image pinning, retry rules, cache record schema, and Recipe context as the existing vector.buffer service.
2. Require the Cell's normalized `target_crs` parameter to resolve to the same CRS as its declared result output contract. A target CRS cannot be silently inferred or changed by the worker.
3. Preflight the source Artifact, checksum, CRS, geometry metadata, geometry validity, target CRS, and availability of a non-ballpark coordinate operation before creating a Run.
4. Execute through a dedicated `DockerVectorReprojectWorker` in the network-disabled worker image. Worker request dispatch is exact on `vector.reproject@1.0.0`; the worker does not choose its own Capability.
5. Independently validate the returned target CRS, FeatureCollection structure, feature count, IDs, properties, geometry types, validity, coordinate finiteness, and dimensionality before registering an output Artifact.
6. Persist the declared target CRS and independently derived geometry types in output Artifact metadata. Preserve input rights and record producer Run/output-port provenance.
7. Reuse the existing exact capability-version Recipe runner registration. A Recipe may compose a reproject Run with another capability Run; upstream Run and Artifact lineage must remain explicit.
8. Keep caching disabled for vector.reproject@1.0.0 until its output-critic evidence and cache compatibility are explicitly versioned. The operation remains deterministic; this is a conservative cache policy, not a claim of nondeterminism.
9. Keep the remote HTTP adapter buffer-specific for now. Local Docker execution of the second capability does not imply remote worker support for it.

## Consequences

- vector.reproject becomes a real Run-producing capability and can be scheduled in sequential Recipes.
- Reprojection output is not trusted merely because the worker returns a successful process result.
- A mixed Recipe can transform coordinates and then run a measurement-sensitive operation such as buffering.
- The current execution model remains sequential. Parallel scheduling, remote reprojection, and cache enablement remain separate work.

## Alternatives considered

- **Treat the kernel's unit tests as sufficient for execution eligibility:** rejected because they do not exercise Run provenance, Artifact integrity, or Recipe lineage.
- **Reuse vector.buffer output validation:** rejected because reprojection must validate target CRS and preserve geometry types and dimensionality rather than requiring polygon outputs and 2D coordinates.
- **Let the worker set output CRS metadata:** rejected because the declared Cell output contract is authoritative.
- **Enable cache immediately:** deferred until cache validation evidence is explicitly compatible with this capability's output critic.
