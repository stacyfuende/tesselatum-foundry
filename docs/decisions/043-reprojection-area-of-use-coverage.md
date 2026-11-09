# ADR-043: Compare geographic input extent with reprojection area of use

- **Status:** Accepted
- **Date:** 2026-11-09
- **Extends:** ADR-039 and ADR-042

## Context

The reprojection worker now records the selected PROJ operation's area-of-use bounds. Recording the bounds alone does not reveal whether the input dataset's declared geographic extent is covered by that operation. Applying an operation outside its published area of use can make the resulting coordinates unsuitable for the intended purpose even when the transformation executes.

Artifact spatial metadata already supports a bounding box in GIS x/y order. A safe first assessment is possible when the input CRS is geographic and the Artifact bbox is present.

## Decision

1. If the input Artifact has a valid geographic CRS, a declared bbox, and the selected operation reports an area of use, compare the complete bbox against the operation's longitude/latitude bounds.
2. Support antimeridian-wrapping operation areas where west is greater than east. A bbox must fit wholly within one of the two longitude intervals to pass.
3. If the bbox is fully contained, record `method.input_extent_within_operation_area_of_use` as passed.
4. If any part of the bbox lies outside the operation area, record the finding as failed with a warning. The Run may still be computationally successful; the methodological report signals that the selected operation's published area does not cover the declared dataset extent.
5. If the source CRS is projected, the bbox is absent/invalid, or the worker reports no area of use, leave coverage not assessed. Do not transform bbox corners with a different control-plane operation and present that as proof of coverage.
6. Treat bbox containment as a conservative extent-level test, not a geometry-by-geometry or positional-accuracy guarantee. Keep coordinate-operation accuracy suitability and purpose-specific tolerances unassessed.

## Consequences

- Runs can identify when the selected PROJ operation's published area does not cover the declared geographic input extent.
- The check is deterministic and uses the worker-reported operation bounds already stored on the output Artifact.
- Projected-source extents and missing bboxes remain explicitly unassessed rather than being approximated with an unrelated transformation.

## Alternatives considered

- **Check only the dataset centroid:** rejected; it can pass while substantial portions of the dataset lie outside the operation area.
- **Transform projected bbox corners in the control plane:** rejected; this would use a separate operation and could understate curved-edge extents.
- **Treat any out-of-area transformation as a computational Run failure:** rejected; the worker may execute correctly while the method remains unsuitable for the intended analytical use.
