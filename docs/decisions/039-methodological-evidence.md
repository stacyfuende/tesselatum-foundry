# ADR-039: Produce operation-specific methodological evidence

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Foundry already performs spatial preflight validation for CRS resolution, projected measurement CRS requirements, horizontal axis units, and explicit CRS transformation boundaries. The execution/output critic intentionally does not assess methodological suitability. A generic quality score would conceal the difference between enforceable operation semantics and analytical suitability that depends on user purpose, area of interest, scale, and acceptable error.

The current Geo-Cell schema does not declare analytical purpose, accuracy tolerance, or an area of interest. The first two vector capabilities nevertheless have explicit methodological semantics and limitations that can be recorded.

## Decision

1. Add a separate `methodological` Validation Report for successful vector.buffer and vector.reproject Runs, including cache-hit Runs.
2. Assess only operation-specific declarations and invariants that Foundry can establish from the exact Capability, Cell parameters/constraints, input Artifact, and output Artifact.
3. For vector.buffer, assess that the measurement CRS is projected, matches the input CRS, the declared unit matches both horizontal CRS axis units, and the distance is finite and positive. Record that the operation is planar.
4. For vector.reproject, assess explicit source/target CRS declarations and that the output Artifact CRS matches the target. Record contract limitations including no segment densification and no antimeridian splitting. Record the non-ballpark requirement as a declared capability constraint, not as a measurement of achieved accuracy.
5. Use `requires_review` when enforceable operation semantics pass but analytical suitability remains unassessed. Use `failed` when a checked declaration or invariant is inconsistent.
6. Explicitly leave purpose, acceptable error tolerance, scale/projection distortion over the area of interest, coordinate-operation accuracy, and area-of-use suitability unassessed where the required context is absent.
7. Do not infer a suitable CRS from its name, silently change parameters, repair geometry, or emit an aggregate quality score.
8. Keep the report separate from execution/output validation and rights/security evidence. A successful computation is not proof that the chosen method is suitable for every analytical purpose.

## Consequences

- Runs expose both what the operation guarantees and what remains a user/domain decision.
- Cache hits receive fresh methodological evidence for the current Run context.
- The report can become more specific as Cell contracts later declare purpose, area of interest, and accuracy requirements.
- Methodological review remains evidence-oriented rather than a single opaque score.

## Alternatives considered

- **Treat schema and spatial preflight success as methodological suitability:** rejected; valid CRS/unit declarations do not establish analytical appropriateness.
- **Introduce a generic quality score:** rejected; it would collapse unrelated assumptions and hide missing context.
- **Block every operation until purpose and tolerance are declared:** deferred; the initial critic should make uncertainty visible without inventing a universal purpose schema.
