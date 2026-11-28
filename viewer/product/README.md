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

The bundle is a portable local handoff. Its manifest carries the product title, intended outcome, audience, decision context, geographic scope, success criteria, acceptance checks, Artifact metadata and execution provenance. After verification, the viewer presents that context as a product handoff above the spatial preview. This is not hosted publishing, a signed distribution channel, or customer access control.

## Current contract

- GeoJSON Feature and FeatureCollection.
- Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon and nested GeometryCollection rendering and coordinate inspection.
- CRS display from the verified Product Manifest Artifact spatial metadata for export bundles; direct RFC 7946 GeoJSON uses its WGS 84 longitude/latitude default. No coordinate transformation is performed.
- Local-only processing; no upload or external map service.
- Product outcome, intended audience, decision context, geographic scope, success criteria and individual acceptance-check status from the verified manifest.
- Feature count, coordinate count, geometry composition, bounding extent, per-feature properties and GeoJSON download.
- Browser preview limit: 50,000 features and 100 MB.

## Important limitations

This is an initial product viewer, not a full GIS renderer. Direct RFC 7946 GeoJSON is interpreted as WGS 84 longitude/latitude. Verified Foundry bundles use the CRS declared in each output Artifact's spatial metadata; if absent, the viewer labels the CRS as undeclared rather than guessing. Projected coordinates are plotted in their native coordinate plane, not transformed or placed on a basemap. The viewer does not render raster formats, perform topology checks, or establish that a dataset is analytically valid. The illustrative sample is not real road data and must not be used for analysis.

## Next integration

The viewer currently opens a user-selected GeoJSON payload. A later product delivery adapter can supply a published Artifact URL and its signed manifest, preserving the same local inspection and validation boundaries.
