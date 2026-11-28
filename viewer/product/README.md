# Spatial Product Viewer

A dependency-free, browser-local preview for GeoJSON spatial products.

## Open a GeoJSON file

Serve this directory as a static site, or open `index.html` in a modern browser. Choose a `.geojson` file, paste a GeoJSON FeatureCollection, or load the clearly labelled illustrative sample.

## Open a Foundry export bundle

1. Build a bundle from an accepted product using `build_geojson_product_bundle`.
2. Extract the ZIP locally.
3. In the viewer, select `product-manifest.json`, `manifest-fingerprint-input.json`, `export-index.json`, and every GeoJSON file under `outputs/` together.
4. Choose **Verify & open bundle**. The viewer checks the exact canonical manifest fingerprint, matches each output to its immutable Artifact identity and metadata, checks file sizes and SHA-256 checksums, then lets you open each output.
5. The browser does not upload files or fetch arbitrary URLs. Use HTTPS or localhost so Web Crypto is available for checksum verification.

The bundle is a portable local handoff. This is not hosted publishing, a signed distribution channel, or customer access control.

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
