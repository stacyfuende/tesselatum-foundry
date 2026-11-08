# v0.1 Acceptance Criteria

**Status:** Planned. These are the definition of done, not claims that the tests already exist or pass.

Acceptance tests must use versioned fixtures and deterministic test inputs. Every test should record the exact schema, capability, implementation, and runtime versions it exercises.

## A. Contract and graph integrity

1. **Valid declaration accepted.** A well-formed Artifact, Capability, Geo-Cell, Run, Recipe, and Validation Report validate against their respective JSON Schemas.
2. **Invalid ports rejected.** A Recipe that references an unknown node, output port, input port, or incompatible port type fails semantic graph validation with a machine-readable finding.
3. **Cycles rejected.** A Recipe containing a dependency cycle fails graph validation. The validator reports the cycle path.

## B. Spatial and methodological correctness

4. **CRS and units enforced.** A buffer declared in metres must declare a projected measurement CRS whose horizontal axis units match the declared unit. An input port with a must_match policy rejects a different input CRS; a different input CRS is allowed only when the capability explicitly declares reproject_to_measurement_crs. Angular units must never be silently treated as metres.
5. **Output contract checked.** A produced output with the wrong data kind, media type, CRS, geometry type, or required validity property fails the applicable output validation.

## C. Execution and provenance

6. **Run is independently recorded.** A valid Recipe executes through a local worker and produces a Run record containing exact cell/capability versions, immutable input artifact versions and checksums, implementation/runtime identity, timestamps, outputs, and validation references.
7. **Retry preserves history.** A failed execution followed by a retry creates a new Run linked to the earlier attempt. The original failed Run remains unchanged and inspectable.
8. **Worker failure is explicit.** Worker loss, timeout, resource exhaustion, and process failure produce structured terminal outcomes and do not register partial outputs as successful artifacts.

## D. Caching and recomputation

9. **Identical inputs produce a valid cache hit.** Repeating a deterministic computation with identical cache-relevant inputs, parameters, implementation, and runtime may reuse the prior validated result. The Run records that it was a cache hit and identifies the source result.
10. **Changed inputs invalidate correctly.** Changing a parameter or input artifact version invalidates the affected computation and its descendants, while independent graph branches remain reusable.

## E. Portability and independent validation

11. **Worker and implementation conformance.** The same logical Run specification can execute through local and remote workers that advertise support. At least two independent vector.buffer implementations (initial candidates: Shapely and PostGIS) pass the same conformance suite, including CRS, units, geometry validity, precision tolerance, edge cases, and failure behaviour.

## Required test evidence

For every acceptance test, retain:
- test identifier and result;
- fixture and fixture version/checksum;
- schema and capability versions;
- implementation and runtime image digest;
- validation findings; and
- logs or structured failure evidence where applicable.

A passing unit test is not a substitute for an end-to-end acceptance test. The v0.1 milestone is complete only when all applicable criteria pass in CI and the evidence is reviewable.
