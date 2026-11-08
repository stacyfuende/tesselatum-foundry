# ADR-041: Declare buffer arc approximation tolerance

- **Status:** Accepted
- **Date:** 2026-11-09
- **Extends:** ADR-040

## Context

Foundry can compute the maximum radial sagitta introduced by `quad_segs`, but without a declared tolerance it cannot determine whether the approximation is acceptable for the intended use. A global default would silently impose an arbitrary quality threshold across different analytical purposes and scales.

## Decision

1. Add optional Geo-Cell constraint `buffer_arc_tolerance` for `vector.buffer`.
2. Express the tolerance in the same unit as the Cell's `linear_unit`; require a positive finite value, a declared linear unit, and an explicit projected measurement CRS.
3. Compare the computed maximum radial sagitta with the declared tolerance:
   - `passed` when the sagitta is less than or equal to the tolerance;
   - `failed` when it exceeds the tolerance;
   - `not_assessed` when no tolerance is declared or the approximation cannot be computed.
4. Do not provide a default tolerance. The caller must choose a value appropriate to the analytical purpose.
5. Preserve the numeric approximation and declared tolerance in the methodological Validation Report.

## Consequences

- A Cell can make buffer arc approximation an explicit, testable acceptance condition.
- A missing tolerance remains visible as unassessed rather than being treated as acceptable.
- The tolerance is distinct from projection scale distortion, positional accuracy, and geodesic suitability.
- Existing Cell definitions remain valid because the constraint is optional.

## Alternatives considered

- **Choose a universal default tolerance:** rejected; the acceptable error depends on intended use.
- **Use a percentage threshold only:** rejected for v0.1; an absolute tolerance in the measurement unit is easier to relate to downstream spatial decisions. Relative error remains reported.
- **Block buffering when no tolerance is supplied:** rejected; Foundry reports the measured approximation and leaves acceptability unassessed.
