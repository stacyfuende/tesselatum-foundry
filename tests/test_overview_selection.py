from __future__ import annotations

from types import SimpleNamespace

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
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



def test_derives_overview_factors_from_odd_grid_dimensions():
    assert overview_factors_from_dimensions(
        5, 5, ((3, 3), (2, 2))
    ) == (2, 3)


@pytest.mark.parametrize("dims", [((5, 5),), ((3, 2),), ((0, 2),)])
def test_rejects_invalid_overview_dimensions(dims):
    with pytest.raises(RasterContractError):
        overview_factors_from_dimensions(5, 5, dims)



def test_overview_factor_derivation_ignores_non_reduced_directories():
    dirs = (
        SimpleNamespace(width=5, height=5, new_subfile_type=0),
        SimpleNamespace(width=3, height=3, new_subfile_type=1),
        SimpleNamespace(width=2, height=2, new_subfile_type=1),
    )
    assert overview_factors_from_tiff_directories(5, 5, dirs) == (2, 3)
