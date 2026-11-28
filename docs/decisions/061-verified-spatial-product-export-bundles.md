# ADR-061: Verified spatial product export bundles

- Status: Proposed for review on PR #24
- Date: 2026-11-28

## Context

The product assembler produces an immutable, provenance-rich manifest, while the initial browser viewer accepts a user-selected GeoJSON file. The local filesystem Artifact Store uses private host-local `file://` URIs; these are not customer delivery URLs and must never be exposed as if they were portable.

## Decision

Add a deterministic export adapter for accepted product manifests. It resolves each output by its exact Artifact ID and version through the configured Artifact Store, compares immutable metadata with the product manifest, reads bytes through the store's checksum-verifying API, and emits a ZIP containing:

- `product-manifest.json`: the accepted source manifest and provenance.
- `export-index.json`: bundle version, product identity, manifest fingerprint, output paths and SHA-256 checksums.
- `outputs/<output-id>.geojson`: supported GeoJSON Feature or FeatureCollection payloads.

Only products with `status=accepted` and `release_allowed=true` are exportable. Manifest fingerprints, Artifact identity/version, media type, size and checksum are checked. Output identifiers are constrained to safe filenames, the export has a configurable aggregate byte limit, and no storage URI or credential is turned into a browser fetch URL. ZIP timestamps and entry order are deterministic.

## Boundaries

- This first adapter supports GeoJSON outputs only. Raster and other formats require format-specific packaging and viewers.
- The bundle is a portable handoff, not hosted publication, signed distribution, access control, or a deployment.
- The filesystem store remains local development storage. A production object-store adapter must preserve immutable identity and verification semantics.
- The viewer integration remains a local open/import step; no arbitrary remote URL fetch is introduced.
