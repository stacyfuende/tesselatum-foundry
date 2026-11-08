# ADR-017: Shared buffer validation and PostGIS realization

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The first Shapely implementation demonstrated the operation boundary, but an engine-independent Capability requires multiple implementations to consume the same validated request and demonstrate equivalent results. Engine-specific input checks risked semantic drift.

## Decision

1. Move parameter, input geometry, CRS and unit validation into a shared engine-neutral request preparation function. Both Shapely and PostGIS MUST consume that normalized request.
2. Implement PostGIS through parameterized SQL using `ST_GeomFromGeoJSON`, `ST_SetSRID` and geometry `ST_Buffer`. Do not use `ST_Transform` or cast to geography; all operations remain planar in the explicitly declared CRS units.
3. The PostGIS adapter requires an unambiguous EPSG identifier because it maps the input CRS to the integer SRID assigned to the PostGIS geometry. The returned geometry SRID MUST equal the input SRID.
4. Translate buffer style values using PostGIS's documented `quad_segs`, `endcap`, `join`, `mitre_limit`, and `side` options. For a single-sided request, only LineString inputs are accepted; positive distance means the left side and end caps are flat in both engines.
5. Both engines ignore Z coordinates during planar buffering and emit 2D polygonal outputs. This is declared capability behaviour, not an accidental implementation detail.
6. Keep the Shapely implementation as an independently callable backend. PostGIS is not a wrapper around Shapely.
7. Maintain one backend-parameterized conformance suite. It checks output geometry types, bounds, areas, validity, CRS, identifiers, properties, and shared rejection rules. A separate test compares the two engine outputs topologically within explicit floating-point tolerances.
8. Run PostGIS conformance in CI against an actual PostGIS service container. Environments without the service may run the Shapely tests while the PostGIS-specific tests are skipped; that is not evidence of two-engine conformance.

## Consequences

The two implementations share validation but execute independently. The PostGIS adapter is limited to CRS definitions that resolve unambiguously to EPSG identifiers. The current capability has two executable realizations, but interchangeability is claimed only after the real PostGIS-backed CI suite passes.

## Alternatives considered

- **Duplicate validation per engine:** rejected because it invites semantic drift.
- **Test only generated SQL or mock a connection:** rejected because that would not demonstrate PostGIS behaviour.
- **Treat matching parameter names as proof of parity:** rejected; conformance is based on actual geometry results and toleranced topological comparison.

## References

- [PostGIS ST_Buffer](https://postgis.net/docs/ST_Buffer.html)
- [Shapely buffer](https://shapely.readthedocs.io/en/stable/reference/shapely.Polygon.html#shapely.Polygon.buffer)
