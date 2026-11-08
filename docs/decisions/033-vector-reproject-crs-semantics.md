# ADR-033: Explicit CRS transformation semantics for vector.reproject

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry's first executable spatial operation, `vector.buffer`, requires a projected measurement CRS and preserves the input CRS. A second capability must exercise genuinely different spatial semantics. Reprojection is a foundational operation, but its behavior is easy to leave ambiguous: axis order, coordinate-operation selection, dimensionality, geometry repair, and output CRS identity all affect reproducibility.

## Decision

1. Introduce `vector.reproject@1.0.0` as a separate engine-independent Capability contract. It accepts one vector FeatureCollection and requires an explicit target CRS parameter.
2. Resolve both source and target CRS from structured Foundry declarations: authority/code or WKT2. Do not infer a CRS from coordinate ranges, file names, or application defaults.
3. Interpret coordinate tuples in x/y order using PROJ's `always_xy=True`, independent of authority axis metadata.
4. Require a non-ballpark coordinate operation and ask PROJ for its best available operation. If required transformation resources are unavailable, fail; do not silently download grids or fall back to a ballpark transform. Worker network access remains disabled.
5. Preserve feature count, IDs, properties, geometry type, and coordinate dimensionality. Reject empty, invalid, or non-finite input and output geometries.
6. Do not repair geometries, densify edges, clip extents, or split antimeridian crossings. Those are distinct operations and must not be hidden side effects of reprojection.
7. Record the requested target CRS as output Artifact metadata. The worker's returned CRS is untrusted and must be checked by the Run service before Artifact registration.
8. Keep the implementation manifest separate from the Capability contract. The Shapely/pyproj realization is not execution-eligible until its conformance suite passes.

## Consequences

- Source and target CRS are explicit, immutable inputs to the computation and therefore part of the deterministic cache identity.
- Axis-order behavior is predictable across EPSG definitions.
- Reprojection fails closed when the local PROJ installation cannot provide an acceptable operation.
- Reprojection is not yet a general geometry normalization or repair tool.
- The capability kernel and contract are introduced separately from Run lifecycle integration; Recipe dispatch must not advertise this capability as executable until its Run service and output critic are implemented.

## Alternatives considered

- **Infer the target CRS from coordinates:** rejected because coordinate ranges are ambiguous and inference is not reproducible.
- **Allow PROJ ballpark transformations:** rejected because they can silently degrade positional accuracy.
- **Allow network grid downloads at execution time:** rejected because it makes execution depend on mutable external resources and violates the isolated-worker boundary.
- **Repair invalid geometries during transformation:** rejected because repair changes topology and is a separate, user-visible operation.
