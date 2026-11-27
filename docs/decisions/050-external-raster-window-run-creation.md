# Decision 050: External raster.window Run creation

## Decision

A Geo-Cell using raster.window may create a queued Run only when its external raster binding, strong ETag, source grid, requested pixel window, selected bands, and output CRS/media contract are explicit and mutually consistent.

The factory does not read source bytes, authorize access, decode TIFF, or publish an Artifact. Those are runtime responsibilities. Source bytes remain in external custody.

## Provenance

The queued Run stores the exact external reference under source_references, no Artifact input snapshot, and normalized parameters including the default target_downsample of 1. Retries must preserve the exact source reference and normalized parameters.

## Boundaries

- Strong ETag is mandatory because multiple byte-range reads must refer to one stable source version.
- Query strings, fragments, embedded credentials, and source-side selection are rejected.
- Window bounds are checked against the declared base grid; execution must still validate against the concrete selected IFD/overview grid.
- Output CRS must equal the source CRS. This capability does not reproject or resample.
- The output is a Foundry raster-window artifact, not GeoTIFF or COG.

## Consequences

This adds a durable control-plane entry point for raster.window while keeping source authorization, bounded range reads, pixel validation, artifact publication, and Run reconciliation as separate auditable gates.
