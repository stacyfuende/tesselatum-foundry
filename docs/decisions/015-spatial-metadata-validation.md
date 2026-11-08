# ADR-015: Spatial metadata semantics and pre-execution validation

- **Status:** Accepted for v0.1
- **Date:** 2026-11-08

## Context

JSON Schema can describe the shape of spatial metadata but cannot resolve CRS definitions, inspect coordinate systems, validate coordinate domains, compare two CRS definitions, or establish that a declared linear unit matches a measurement CRS. Those checks are necessary before a spatial computation is dispatched to a worker.

A bounding-box array also needs a stable coordinate ordering. Leaving the ordering implicit makes extents ambiguous, especially for six-dimensional coordinate tuples and authority-defined CRSs whose axis order differs from common GIS x/y conventions.

## Decision

1. Spatial Artifact metadata for vector, raster, point-cloud and mesh data requires a resolvable CRS. Raster artifacts also require grid dimensions.
2. A 2D extent is [min_x, min_y, max_x, max_y]. A 3D extent is [min_x, min_y, min_z, max_x, max_y, max_z]. Coordinates use GIS x/y order independent of authority axis order.
3. Extents must contain finite values and each minimum must not exceed its corresponding maximum. Geographic x/y values are checked against the longitude/latitude domain using the CRS angular units. Antimeridian-crossing extents are not encoded by reversing minima and maxima.
4. Capability input and output ports may declare CRS-required, CRS-kind, geometry-type, same-CRS-as, and measurement-CRS handling constraints. A must_match policy requires an input CRS to equal the Geo-Cell measurement CRS. A reproject_to_measurement_crs policy explicitly permits a capability implementation to transform that input internally; this behavior must be covered by implementation conformance tests.
5. A Geo-Cell declaring a linear measurement unit must also declare a measurement CRS. The CRS must be projected and its horizontal axis units must match the declared unit.
6. CRS parsing and axis inspection use PROJ through the pyproj dependency.
7. These checks do not authorize implicit input reprojection. Required transformations must be explicit in the computation graph or explicitly guaranteed by a separately versioned capability contract.

## Consequences

- Spatial metadata can be checked before worker dispatch.
- Invalid CRS definitions, impossible geographic extents, incompatible input metadata and measurement-unit mismatches produce machine-readable findings.
- The common schema defines the extent shape; semantic validation enforces the coordinate meaning.
- Foundry's internal bbox convention is independent of CRS authority axis ordering and must be preserved by all adapters.

## Alternatives considered

- Treat CRS as an opaque string and defer all checks to GIS engines: rejected because invalid declarations should be caught before execution.
- Assume all coordinates are longitude/latitude: rejected because Foundry must support projected and other CRS types.
- Silently reproject inputs to make an operation work: rejected because it hides computation and provenance from the graph.
- Encode antimeridian crossing as min_x > max_x: rejected because it conflicts with ordinary extent ordering and complicates generic validation.
