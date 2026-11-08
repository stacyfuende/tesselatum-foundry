# ADR-040: Quantify buffer arc approximation and record shape semantics

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The vector.buffer contract exposes `quad_segs`, `cap_style`, `join_style`, and `mitre_limit`. These parameters affect the constructed geometry, not merely worker implementation details. The methodology critic previously recorded the planar distance model but did not quantify the approximation introduced when circular arcs are represented by straight segments.

For a circular buffer of radius `r` with `q` segments per quadrant, the maximum radial sagitta between a chord and its circular arc is:

`r * (1 - cos(pi / (4*q)))`.

The relative error can be computed without knowing the analytical purpose. Whether that error is acceptable still requires an explicit tolerance.

## Decision

1. Record and validate `quad_segs` as an integer from 1 through 64.
2. Compute the maximum radial sagitta and its percentage of the requested buffer distance using the exact `quad_segs` and distance used by the Run.
3. Mark acceptability as `not_assessed` until the Cell declares an applicable tolerance. Do not convert the computed approximation into a generic quality score.
4. Record `cap_style`, `join_style`, and `mitre_limit`. Explicitly state that `mitre_limit` applies only when `join_style` is `mitre`.
5. Preserve the distinction between arc approximation error and projection scale distortion, geodesic distance suitability, and other analytical accuracy concerns.

## Consequences

- Methodological reports expose a concrete, reproducible geometric approximation value.
- Users can compare the value with a purpose-specific tolerance once one is declared.
- Shape construction semantics remain visible in immutable Run evidence.
- A future tolerance contract can assess acceptability without changing the calculation or rewriting historical reports.

## Alternatives considered

- **Treat the default `quad_segs` as universally adequate:** rejected; acceptability depends on radius and use-specific tolerance.
- **Report only the parameter value:** rejected; the geometric effect is directly computable and should be made explicit.
- **Combine arc approximation, projection distortion, and coordinate accuracy into one score:** rejected; these are distinct error sources.
