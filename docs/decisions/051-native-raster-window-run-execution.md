# Decision 051: Native raster.window Run execution

## Decision

Execute the initial `raster.window@1.0.0` Capability through a native Foundry runtime, recorded explicitly as `worker_type: local_native`. Do not mislabel the in-process TIFF reader as a Docker or remote worker.

## Execution sequence

1. Verify queued Run, exact Cell/Capability identity and immutable source reference.
2. Authorize the actor and resolve an allowlisted source adapter at execution time.
3. Describe the source and require a trustworthy file size.
4. Use one cumulative strong-ETag-pinned range budget for base TIFF metadata, directory indexing and tile reads.
5. Compare observed dimensions, band count and embedded CRS with the external Geo-Cell declaration.
6. Select a concrete base/overview IFD, read the requested tiled window and construct explicit NoData validity.
7. Run the independent raster output critic and persist an execution-output Validation Report.
8. Encode the versioned Foundry Raster Window Container and publish through the immutable content-addressed Artifact store.
9. Reconcile the committed Artifact with the Run using its producer identity and passing Validation Report.

## Artifact format

The output is `application/vnd.tessellatum.raster-window`, format `tessellatum-raster-window/1.0.0`. It contains raw sample bytes, an explicit packed validity bitset, a canonical JSON header, the window-local affine transform and source/IFD provenance. It is not GeoTIFF or COG.

## Recovery

Artifact publication is immutable and content-addressed. If Artifact metadata commits but Run reconciliation is interrupted, the orchestrator can reconcile from the Artifact's producer Run/attempt and Validation Report reference. This does not resume interrupted source reads; a durable raster publication journal and restart policy remain a separate gate.

## Consequences

Raster execution now has a real control-plane-to-Artifact path without ingesting source datasets or inventing worker infrastructure. The implementation manifest remains `not_run` until CI validates the end-to-end suite; conformance must not be pre-claimed.
