# ADR-016: First executable capability — vector.buffer

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry has a contracts-first domain model and spatial metadata validation, but no implemented spatial operation. Buffering is a useful first capability because it exercises geometry handling, projected measurement, parameter semantics, output typing, and implementation conformance without requiring a broad GIS runtime.

## Decision

1. Define `vector.buffer@1.0.0` as an engine-independent capability contract.
2. The first implementation uses Shapely and accepts a GeoJSON FeatureCollection plus explicit input and measurement CRS metadata.
3. Buffering is planar. Input CRS MUST equal the projected measurement CRS. Foundry MUST NOT reproject or convert distance units implicitly.
4. The distance parameter is positive and expressed in the native horizontal axis unit declared by the Geo-Cell's `linear_unit` constraint.
5. Input geometries MUST be non-empty, valid, and one of Point, MultiPoint, LineString, MultiLineString, Polygon, or MultiPolygon. Invalid input is rejected, not silently repaired.
6. Output geometries MUST be valid, non-empty Polygon or MultiPolygon geometries. Feature IDs and properties are preserved, and output CRS equals input CRS.
7. Buffer style parameters are explicit and have portable defaults: 8 quadrant segments, round cap, round join, mitre limit 5, and not single-sided.
8. The Shapely implementation is the first realization only. PostGIS is a separate implementation and MUST pass the same conformance cases before the two are described as interchangeable.

## Consequences

The implementation can be exercised without introducing a worker scheduler or run lifecycle prematurely. It establishes a reusable operation boundary and tests real geometry results. It does not yet constitute an end-to-end Foundry execution path, artifact persistence, or PostGIS parity.

## Alternatives considered

- **Allow automatic reprojection:** rejected because it hides a material analytical transformation and can change measurements.
- **Repair invalid geometries automatically:** rejected because repair can alter topology and must be an explicit upstream operation.
- **Treat GeoJSON as inherently WGS84:** rejected for this internal capability boundary; CRS is supplied explicitly as artifact metadata. Serialization/export policy must separately ensure that the chosen media type and CRS representation are standards-compliant.
- **Claim cross-engine equivalence from matching parameter names:** rejected; equivalence requires shared conformance tests against actual engine results.
