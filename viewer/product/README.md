# Spatial Product Viewer

A dependency-free, browser-local preview for GeoJSON spatial products.

## Open

Serve this directory as a static site, or open `index.html` in a modern browser. Choose a `.geojson` file, paste a GeoJSON FeatureCollection, or load the clearly labelled illustrative sample.

## Current contract

- GeoJSON Feature and FeatureCollection.
- Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon and GeometryCollection coordinate inspection (GeometryCollection geometry rendering is not yet implemented).
- Local-only processing; no upload or external map service.
- Feature count, coordinate count, geometry composition, bounding extent, per-feature properties and GeoJSON download.
- Browser preview limit: 50,000 features and 100 MB.

## Important limitations

This is an initial product viewer, not a full GIS renderer. It assumes GeoJSON longitude/latitude coordinates (RFC 7946 / WGS 84). It does not transform projected coordinates, provide a basemap, render raster formats, perform topology checks, or establish that a dataset is analytically valid. GeometryCollection and mixed/unsupported render geometries are not yet drawn. The illustrative sample is not real road data and must not be used for analysis.

## Next integration

The viewer currently opens a user-selected GeoJSON payload. A later product delivery adapter can supply a published Artifact URL and its signed manifest, preserving the same local inspection and validation boundaries.
