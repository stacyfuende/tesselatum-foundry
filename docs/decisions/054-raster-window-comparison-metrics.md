# ADR-054: Exact-grid raster-window numeric comparison

## Status
Proposed for review on PR #24

## Context
Foundry now produces bounded, provenance-bearing raster-window Artifacts. Experiments need a first comparison capability that measures differences without silently aligning, resampling, or reprojecting inputs.

## Decision
Add a pure comparison routine for decoded or encoded TFRW 1.0.0 Artifacts. It requires exact matching pixel windows, CRS, affine transforms, band ordering, and pixel interleave. Metrics are calculated over the intersection of the two validity masks. Report validity overlap separately from numeric metrics.

Per-band measures: sample count, bias (B minus A), mean absolute error, RMSE, maximum absolute difference, means of both inputs, and Pearson correlation when defined.

## Boundaries
This is not raster alignment, resampling, categorical confusion analysis, uncertainty/sensitivity analysis, or scientific interpretation. No input is modified. The comparison output is a JSON-compatible report; persistence as an Artifact and Experiment-level aggregation are later steps.

## Consequences
The first comparator makes exact-grid method/parameter comparisons measurable. Experiments whose outputs use different grids must explicitly plan an alignment operation before comparison, rather than relying on hidden normalization.
