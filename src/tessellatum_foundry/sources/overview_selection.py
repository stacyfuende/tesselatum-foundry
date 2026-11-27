"""Deterministic overview choice for raster reads."""
from __future__ import annotations

import math

from collections.abc import Iterable\n\nfrom .raster import RasterContractError, RasterMetadata


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
        or not math.isfinite(target_downsample)
        or target_downsample < 1
    ):
        raise RasterContractError("Target downsample must be a number >= 1.")
    factors = metadata.overview_factors
    eligible = [factor for factor in factors if factor <= target_downsample]
    return max(eligible, default=1)

\n\ndef overview_factors_from_dimensions(
    base_width: int,
    base_height: int,
    overview_dimensions: Iterable[tuple[int, int]],
) -> tuple[int, ...]:
    """Derive conservative integer overview factors from dimensions.

    Accepts only matching horizontal/vertical integer reductions and dimensions
    consistent with ceil(base/factor), which accommodates odd-sized grids.
    Invalid dimensions fail rather than silently entering the overview metadata.
    """
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (base_width, base_height)
    ):
        raise RasterContractError("Base raster dimensions must be positive integers.")
    factors = set()
    for width, height in overview_dimensions:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (width, height)
        ):
            raise RasterContractError("Overview dimensions must be positive integers.")
        if width >= base_width or height >= base_height:
            raise RasterContractError("Overview dimensions must be smaller than the base grid.")
        fx = base_width / width
        fy = base_height / height
        factor = round(fx)
        if factor < 2 or abs(fx - factor) > 1e-9 or abs(fy - factor) > 1e-9:
            raise RasterContractError("Overview dimensions do not imply a consistent integer factor.")
        if width != (base_width + factor - 1) // factor or height != (
            base_height + factor - 1
        ) // factor:
            raise RasterContractError("Overview dimensions are inconsistent with reduction factor.")
        factors.add(factor)
    return tuple(sorted(factors))
