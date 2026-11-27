"""Deterministic overview choice and TIFF directory binding for raster reads."""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace

from .raster import RasterContractError, RasterMetadata
from .tiff import TiffDirectory


@dataclass(frozen=True, slots=True)
class SelectedTiffOverview:
    """A concrete TIFF directory paired with metadata on that directory's grid."""

    factor: int
    directory: TiffDirectory
    metadata: RasterMetadata


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
    """Derive unique integer factors using bounded arithmetic, including odd grids."""
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (base_width, base_height)
    ):
        raise RasterContractError("Base raster dimensions must be positive integers.")

    maximum = max(base_width, base_height)
    factors: set[int] = set()
    for dimensions in overview_dimensions:
        if not isinstance(dimensions, (tuple, list)) or len(dimensions) != 2:
            raise RasterContractError("Overview dimensions must be width/height pairs.")
        width, height = dimensions
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (width, height)
        ):
            raise RasterContractError("Overview dimensions must be positive integers.")
        if width >= base_width or height >= base_height:
            raise RasterContractError("Overview dimensions must be smaller than the base grid.")

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
    directories: Iterable[TiffDirectory],
) -> tuple[int, ...]:
    """Derive overview factors from directories marked reduced-resolution."""
    reduced = [
        (directory.width, directory.height)
        for directory in directories
        if directory.new_subfile_type & 1
    ]
    return overview_factors_from_dimensions(base_width, base_height, reduced)


def select_tiff_overview(
    directories: Iterable[TiffDirectory],
    metadata: RasterMetadata,
    *,
    target_downsample: float,
) -> SelectedTiffOverview:
    """Choose an indexed TIFF IFD and produce metadata aligned to its pixel grid.

    The directory index must come from TiffRangeReader.read_directory_index().
    Selection is fail-closed: duplicate base IFDs, ambiguous overview dimensions,
    unsupported strip layouts, or inconsistent band metadata are rejected.
    """
    indexed = tuple(directories)
    base_matches = [
        directory for directory in indexed
        if not (directory.new_subfile_type & 1)
        and (directory.width, directory.height) == (metadata.width, metadata.height)
    ]
    if len(base_matches) != 1:
        raise RasterContractError("TIFF index must contain exactly one matching base image directory.")

    factors = overview_factors_from_tiff_directories(
        metadata.width, metadata.height, indexed
    )
    enriched = replace(metadata, overview_factors=factors)
    factor = select_overview_factor(enriched, target_downsample=target_downsample)
    if factor == 1:
        directory = base_matches[0]
    else:
        expected_dimensions = (
            (metadata.width + factor - 1) // factor,
            (metadata.height + factor - 1) // factor,
        )
        matches = [
            item for item in indexed
            if item.new_subfile_type & 1
            and (item.width, item.height) == expected_dimensions
        ]
        if len(matches) != 1:
            raise RasterContractError("Selected TIFF overview does not map to exactly one image directory.")
        directory = matches[0]

    if directory.samples_per_pixel != metadata.band_count:
        raise RasterContractError("Selected TIFF directory band count does not match raster metadata.")
    if not directory.tiled or directory.tile_width is None or directory.tile_height is None:
        raise RasterContractError("Selected TIFF overview is not tiled and cannot use tile-window reads.")

    transform = list(metadata.transform)
    for index in (1, 2, 4, 5):
        transform[index] *= factor
    selected_metadata = replace(
        enriched,
        width=directory.width,
        height=directory.height,
        transform=tuple(transform),
        block_shapes=tuple(
            (directory.tile_height, directory.tile_width)
            for _ in range(metadata.band_count)
        ),
    )
    return SelectedTiffOverview(factor, directory, selected_metadata)
