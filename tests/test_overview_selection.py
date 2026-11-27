from __future__ import annotations

from types import SimpleNamespace

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    overview_factors_from_dimensions,
    overview_factors_from_tiff_directories,
    select_overview_factor,
    select_tiff_overview,
    select_tiff_tiles,
    RasterWindow,
)


def metadata(factors, width=2048, height=2048):
    return RasterMetadata(
        width=width, height=height, band_count=1, dtypes=("uint8",),
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
    assert overview_factors_from_dimensions(8, 8, ((4, 4),)) == (2,)


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



def tiff_directory(width, height, *, reduced, tile_width=16, tile_height=16, offset=0):
    across = (width + tile_width - 1) // tile_width
    down = (height + tile_height - 1) // tile_height
    return SimpleNamespace(
        offset=offset, width=width, height=height, tiled=True,
        block_offsets=tuple(range(100 + offset, 100 + offset + across * down)),
        block_byte_counts=tuple(64 for _ in range(across * down)),
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=tile_width, tile_height=tile_height,
        samples_per_pixel=1, planar_configuration=1, compression=1,
        new_subfile_type=1 if reduced else 0, predictor=1,
    )


def test_binds_selected_overview_directory_to_scaled_grid_metadata():
    base = tiff_directory(64, 64, reduced=False, offset=1)
    overview = tiff_directory(32, 32, reduced=True, offset=2)
    selected = select_tiff_overview(
        (base, overview), metadata((2, 4), width=64, height=64), target_downsample=2
    )
    assert selected.factor == 2
    assert selected.directory is overview
    assert (selected.metadata.width, selected.metadata.height) == (32, 32)
    assert selected.metadata.transform == (0, 2, 0, 0, 0, -2)
    assert selected.metadata.block_shapes == ((16, 16),)


def test_rejects_missing_or_ambiguous_base_directory():
    base = tiff_directory(64, 64, reduced=False)
    with pytest.raises(RasterContractError):
        select_tiff_overview(
            (base, base), metadata((), width=64, height=64), target_downsample=1
        )


def test_rejects_non_tiled_selected_overview():
    base = tiff_directory(64, 64, reduced=False)
    overview = tiff_directory(32, 32, reduced=True)
    overview = SimpleNamespace(**{**overview.__dict__, "tiled": False})
    with pytest.raises(RasterContractError):
        select_tiff_overview(
            (base, overview), metadata((2,), width=64, height=64), target_downsample=2
        )



def test_selected_overview_directory_drives_actual_tile_window_selection():
    base = tiff_directory(64, 64, reduced=False, offset=1)
    overview = tiff_directory(32, 32, reduced=True, offset=2)
    selected = select_tiff_overview(
        (base, overview), metadata((), width=64, height=64), target_downsample=2
    )
    tiles = select_tiff_tiles(
        selected.directory,
        selected.metadata,
        RasterWindow(row_offset=0, column_offset=0, height=16, width=16),
    )
    assert len(tiles) == 1
    assert tiles[0].block_index == 0
    assert tiles[0].byte_offset == overview.block_offsets[0]
