# ADR-052: Live external Nairobi raster conformance

- **Status:** Accepted for the raster.window 1.0.0 implementation
- **Date:** 2026-11-27
- **Scope:** External STAC discovery, HTTPS range access, TIFF window execution, validation and Artifact publication

## Decision

Foundry's first real-source raster conformance check uses the public Element 84 Earth Search STAC API and a Sentinel-2 Level-2A red-band Cloud-Optimized GeoTIFF intersecting Nairobi, Kenya.

The smoke test is executed by GitHub Actions in a separate job that does not depend on the PostGIS service. It dynamically discovers a current item, resolves the `red` asset through the STAC resolver, obtains a strong ETag from the asset endpoint, and uses the allowlisted `HttpSourceAdapter` for conditional HTTP range reads.

The test then reads the TIFF metadata, declares an external raster Geo-Cell using the observed grid and authority CRS, creates a queued `raster.window@1.0.0` Run, and executes the existing native orchestrator. The output is independently inspected, published as an immutable Foundry Raster Window Container Artifact, read back and checksum-verified.

## Observed conformance result

GitHub Actions run [#1053](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/46030882354), live external raster job, completed successfully.

- STAC collection: `sentinel-2-l2a`
- Item: `S2B_37MBU_20261123_0_L2A`
- Asset: `red`
- Source host: `sentinel-cogs.s3.us-west-2.amazonaws.com`
- Source object size: 233,794,870 bytes
- Bytes requested by Foundry: 1,483,357
- HTTP range requests: 47
- Fraction of source object read: 0.006345 (about 0.63%)
- Observed grid: 10,980 × 10,980 pixels
- Observed CRS: EPSG:32737
- Output window: 64 × 64 pixels
- Independent validation: passed
- Run state: succeeded
- Output Artifact SHA-256: `3a17ad2add0d16b224bede8724d00116bb2e5419767d0673cde1190cbb958023`

The test verifies that the output Artifact can be retrieved, its content-addressed bytes verified and its raster-window envelope decoded. The temporary CI workspace is removed at job completion; this is an execution conformance test, not a persistent production deployment.

## Defect found and corrected

The first live execution reached the external COG and parsed its metadata, but failed during window assembly. Deflate decoding had changed the decoded tile's selection byte length to the decompressed length. The assembler compares decoded tiles to the original source selections, whose byte lengths describe compressed ranges. Synthetic uncompressed tests did not expose the mismatch.

The decoder now validates and decodes against the decompressed length internally while preserving the original compressed source selection on the returned decoded tile. A regression assertion verifies that Deflate decoding retains the original selection identity. The same real-source test then passed through assembly, independent validation and publication.

## What this proves

- A public STAC catalogue can be queried to discover a real spatial asset.
- The STAC asset can be converted to a provider-neutral external reference.
- Foundry can obtain and enforce a strong source ETag.
- The HTTP adapter can retrieve bounded byte ranges from the actual remote COG.
- Foundry can parse real GeoTIFF grid and CRS metadata.
- The native `raster.window` Run can execute against the external source.
- The output can be independently validated and published as an immutable Artifact.
- The source dataset remains external; Foundry reads a small fraction of its bytes.

## What this does not yet prove

- Every STAC provider, cloud host, TIFF variant, compression codec or predictor is supported.
- Full formal COG conformance or every overview layout is certified.
- Source licensing and downstream rights are automatically established.
- CRS transformation, reprojection, destination-grid resampling or GeoTIFF/COG export are implemented by this path.
- Durable restart of an interrupted remote read is implemented.
- Production credentials, provider-specific authorization, service-level availability or large-scale throughput have been validated.

## Consequences

The live-source smoke test is retained as an independent CI job. It uses a public Nairobi-area Sentinel-2 asset and asserts that Foundry reads less than the full source object, publishes a valid 64 × 64 window, and completes the Run successfully. The discovered Deflate identity regression is now covered by the unit suite as well as the live integration test.
