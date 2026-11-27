from __future__ import annotations

from types import SimpleNamespace

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    overview_factors_from_dimensions,
    overview_factors_from_tiff_directories,
    select_overview_factor,
)


def metadata(factors):
    return RasterMetadata(
        width=2048, height=2048, band_count=1, dtypes=("uint8",),
        transform=(0, 1, 0, 0, 0, -1), overview_factors=tuple(factors),
    )


@pytest.mark.parametrize(
    ("factors", "target", "expected"),
    [
        ((), 4, 1),
        ((2, 4, 8), 1, 1),
        ((2, 4, 8), 3, 2),
        ((2, 4, 8), 4, 4),
        ((2, 4, 8), 7, 4),
        ((2, 4, 8), 16, 8),
    ],
)
def test_selects_coarsest_overview_not_exceeding_target(factors, target, expected):
    assert select_overview_factor(metadata(factors), target_downsample=target) == expected


@pytest.mark.parametrize("target", [0, -1, True, float("nan"), float("inf"), "4"])
def test_rejects_invalid_downsample_target(target):
    with pytest.raises(RasterContractError):
        select_overview_factor(metadata((2, 4)), target_downsample=target)


def test_derives_unique_factor_from_dimensions_without_scanning_grid_size():
    assert overview_factors_from_dimensions(
        100_000_000, 100_000_000, ((50_000_000, 50_000_000),)
    ) == (2,)


def test_derives_overview_factors_from_even_grid_dimensions():
    assert overview_factors_from_dimensions(8, 8, ((4, 4),)) == (2)


@pytest.mark.parametrize(
    "args",
    [
        (0, 8, ()),
        (8, 8, ((8, 4),)),
        (8, 8, ((0, 4),)),
        (8, 8, ((4, 3),)),
        (5, 5, ((2, 2),)),  # both factors 3 and 4 produce ceil(5/factor) == 2
    ],
)
def test_rejects_invalid_or_ambiguous_overview_dimensions(args):
    with pytest.raises(RasterContractError):
        overview_factors_from_dimensions(*args)


def test_overview_factor_derivation_ignores_non_reduced_directories():
    dirs = (
        SimpleNamespace(width=8, height=8, new_subfile_type=0),
        SimpleNamespace(width=4, height=4, new_subfile_type=1),
    )
    assert overview_factors_from_tiff_directories(8, 8, dirs) == (2,)
