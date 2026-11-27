"""Deterministic overview choice for raster reads."""
from __future__ import annotations

import math
from collections.abc import Iterable

from .raster import RasterContractError, RasterMetadata


def select_overview_factor(
    metadata: RasterMetadata,
    *,
    target_downsample: float,
) -> int:
    """Select the coarsest available overview not exceeding requested reduction."""
    if (
        isinstance(target_downsample, bool)
        or not isinstance(target_downsample, (int, float))
        or not math.isfinite(target_downsample)
        or target_downsample < 1
    ):
        raise RasterContractError("Target downsample must be a number >= 1.")
    eligible = (
        factor for factor in metadata.overview_factors
        if factor <= target_downsample
    )
    return max(eligible, default=1)


def _factor_interval(base: int, reduced: int, maximum: int) -> tuple[int, int]:
    """Return integer factors satisfying ceil(base/factor) == reduced."""
    lower = (base + reduced - 1) // reduced
    upper = maximum if reduced == 1 else (base - 1) // (reduced - 1)
    return lower, upper


def overview_factors_from_dimensions(
    base_width: int,
    base_height: int,
    overview_dimensions: Iterable[tuple[int, int]],
) -> tuple[int, ...]:
    """Derive unique integer factors using bounded arithmetic, including odd grids.

    The interval intersection avoids scanning every possible factor, which
    would make a small metadata operation proportional to raster dimensions.
    Only reduced-resolution dimensions consistent with ceil(base/factor) pass.
    """
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (base_width, base_height)
    ):
        raise RasterContractError("Base raster dimensions must be positive integers.")

    maximum = max(base_width, base_height)
    factors: set[int] = set()
    for dimensions in overview_dimensions:
        if (
            not isinstance(dimensions, (tuple, list))
            or len(dimensions) != 2
        ):
            raise RasterContractError("Overview dimensions must be width/height pairs.")
        width, height = dimensions
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (width, height)
        ):
            raise RasterContractError("Overview dimensions must be positive integers.")
        if width >= base_width or height >= base_height:
            raise RasterContractError(
                "Overview dimensions must be smaller than the base grid."
            )

        width_min, width_max = _factor_interval(base_width, width, maximum)
        height_min, height_max = _factor_interval(base_height, height, maximum)
        lower = max(2, width_min, height_min)
        upper = min(maximum, width_max, height_max)
        if lower != upper:
            raise RasterContractError(
                "Overview dimensions do not imply a unique integer reduction factor."
            )
        factor = lower
        if (
            (base_width + factor - 1) // factor != width
            or (base_height + factor - 1) // factor != height
        ):
            raise RasterContractError(
                "Overview dimensions do not match a common integer reduction factor."
            )
        factors.add(factor)
    return tuple(sorted(factors))


def overview_factors_from_tiff_directories(
    base_width: int,
    base_height: int,
    directories: Iterable[object],
) -> tuple[int, ...]:
    """Derive overview factors from reduced-resolution TIFF directories.

    Only directories marked with NewSubfileType bit 0 are considered. The
    caller must supply directories from a bounded, validated TIFF index.
    """
    reduced = [
        (directory.width, directory.height)
        for directory in directories
        if getattr(directory, "new_subfile_type", 0) & 1
    ]
    return overview_factors_from_dimensions(base_width, base_height, reduced)
