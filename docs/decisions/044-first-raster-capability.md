# ADR-044: Establish raster.band_statistics as the first raster capability

- **Status:** Accepted for the initial raster capability slice
- **Date:** 2026-11-09

## Context

Foundry's Artifact and spatial metadata models already recognize raster data, including CRS, grid dimensions, band count, resolution, and nodata. The executable capability catalogue, however, is vector-only. Raster support needs to begin with a narrow, deterministic operation that establishes raster-specific semantics and a conformance pattern before introducing resampling, mosaicking, or analysis algorithms.

## Decision

1. Introduce `raster.band_statistics@1.0.0` as the first raster capability.
2. Accept a georeferenced raster Artifact as an immutable byte input and select bands using optional 1-based indexes; omission selects all bands.
3. Calculate statistics exhaustively over every valid pixel in each selected band. Do not sample or approximate.
4. Exclude GDAL-masked and nodata pixels. Reject a selected band with no finite valid samples.
5. Report minimum, maximum, mean, population standard deviation, and valid-pixel count for each band.
6. Report stored-value scale, offset, and unit metadata, but do not apply scale/offset to sample values. The output explicitly identifies raw stored-sample semantics.
7. Require a resolvable source CRS. Preserve raster dimensions and identify the source CRS in the result.
8. Use Rasterio/GDAL and NumPy for the first implementation. Keep the dependency optional through the `raster` extra.
9. Reopen the source raster in a separate output critic and recompute source-derived statistics before accepting a result. The critic is a separate code path but currently shares the Rasterio/GDAL and NumPy dependency family; it is not yet an independent-engine cross-check.
10. Treat the implementation's conformance state as not_run until the canonical suite and installed-distribution checks pass in CI. Do not dispatch it through the Run service before its runtime, output validation, and conformance gate are integrated.

## Consequences

- Foundry gains a first executable raster kernel and explicit band-statistics semantics.
- The implementation is deterministic for a fixed raster byte sequence and runtime stack.
- Statistics describe raw stored samples, which is important for scaled integer imagery and must be visible to consumers.
- This capability does not alter raster pixels and does not yet provide an end-to-end raster Run, Artifact output, or Recipe execution path.

## Deliberate exclusions

This version does not reproject, resample, warp, mosaic, clip, classify, calculate zonal statistics, infer units, apply scale/offset, or interpret color maps. It does not claim suitability for a particular scientific or operational purpose.

## Numerical precision refinement

The window accumulator preserves integer extrema as Python integers. For integer bands, it accumulates an exact integer sum (using NumPy limb reductions for 64-bit samples) and converts the final quotient to the float64 mean output; this avoids cancellation errors when signed samples span both ends of the int64 range. Separately, it subtracts a fixed per-band integer baseline before converting deltas to float64 for mergeable population-variance accumulation, preserving adjacent large samples when their offsets are representable. The independent critic implements its own source-derived exact-sum and variance path and compares integer extrema exactly. Mean and population standard deviation remain float64 outputs; variance is not arbitrary-precision. Regression coverage includes adjacent int64 values near 2^60, adjacent uint64 values near the uint64 maximum, and the full int64 range. This is an exhaustive scan of valid samples, not a claim of exact real-number arithmetic.
