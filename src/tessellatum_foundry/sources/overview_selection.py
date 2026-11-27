"""Deterministic overview choice for raster reads."""
from __future__ import annotations

from .raster import RasterContractError, RasterMetadata


def select_overview_factor(
    metadata: RasterMetadata,
    *,
    target_downsample: float,
) -> int:
    """Select the coarsest available overview not exceeding requested reduction.

    Factor 1 denotes the full-resolution image. Choosing an overview larger
    than target_downsample would undersample the requested output, so it is
    deliberately avoided. If no overview qualifies, return 1.
    """
    if (
        isinstance(target_downsample, bool)
        or not isinstance(target_downsample, (int, float))
        or not math.isfinite(target_downsample)\n        or target_downsample < 1
    ):
        raise RasterContractError("Target downsample must be a number >= 1.")
    factors = metadata.overview_factors
    eligible = [factor for factor in factors if factor <= target_downsample]
    return max(eligible, default=1)
