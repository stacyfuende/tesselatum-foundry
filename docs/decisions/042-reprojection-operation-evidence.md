# ADR-042: Capture the coordinate operation selected by the reprojection worker

- **Status:** Accepted
- **Date:** 2026-11-09
- **Extends:** ADR-039

## Context

The methodology critic could establish that vector.reproject requires a non-ballpark operation, but it did not know which operation PROJ actually selected at execution time. Recomputing a likely operation in the control plane would be unsafe: its PROJ database, grid availability, and version may differ from the pinned worker runtime.

The worker already creates and uses a `pyproj.Transformer` for every feature. That same object exposes the selected operation description, pipeline definition, reported accuracy, and area of use after transformation.

## Decision

1. Capture operation evidence from the exact `Transformer` instance used to transform the input coordinates, after the transformation has executed.
2. Record:
   - operation description;
   - PROJ pipeline definition when available and within the bounded evidence size;
   - PROJ-reported accuracy in metres, or `null` when unknown;
   - area-of-use bounds and name, or `null` when unavailable.
3. Carry the evidence through local Docker and authenticated remote worker responses in the `WorkerResult` envelope.
4. Validate the untrusted evidence in the control plane before accepting a successful reprojection Run. Bound description and pipeline sizes; require finite accuracy and valid longitude/latitude bounds when those values are present. Permit west-greater-than-east bounds to represent antimeridian-wrapping areas.
5. Persist the evidence in immutable output Artifact metadata and reference it in the Run's methodological Validation Report.
6. Reject legacy or malformed reprojection cache candidates that lack valid operation identity evidence. A cache hit must not hide the fact that the selected operation was not recorded.
7. Distinguish a reported accuracy value from accuracy suitability. Without a Cell-declared tolerance and area-of-interest coverage requirement, those suitability dimensions remain unassessed.

## Consequences

- The record describes the operation actually used by the worker, not a control-plane reconstruction.
- The output Artifact preserves the selected operation identity alongside the worker runtime digest and Run provenance.
- Unknown PROJ accuracy remains explicitly unknown; it is never converted to zero or inferred from the CRS pair.
- Cache reuse remains reproducible with respect to the operation evidence recorded by the producing worker.

## Alternatives considered

- **Reconstruct the operation in the control plane:** rejected; PROJ versions and grid availability may differ from the execution environment.
- **Record only source and target CRS:** rejected; multiple coordinate operations may exist for the same CRS pair.
- **Treat PROJ-reported accuracy as a universal pass/fail:** rejected; acceptability depends on the intended purpose and tolerance.
