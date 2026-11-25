from __future__ import annotations

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    TiffDirectory,
    select_tiff_tiles,
)


def make_metadata(width=600, height=500, bands=1):
    return RasterMetadata(
        width=width, height=height, band_count=bands,
        dtypes=("uint8",) * bands,
        transform=(0, 1, 0, 0, 0, -1),
    )


def make_directory(*, width=600, height=500, tile_width=256, tile_height=256,
                   bands=1, planar=1):
    across = (width + tile_width - 1) // tile_width
    down = (height + tile_height - 1) // tile_height
    planes = 1 if planar == 1 else bands
    count = across * down * planes
    return TiffDirectory(
        offset=8, width=width, height=height, tiled=True,
        block_offsets=tuple(1000 + i * 100 for i in range(count)),
        block_byte_counts=tuple(50 + i for i in range(count)),
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=tile_width, tile_height=tile_height,
        samples_per_pixel=bands, planar_configuration=planar,
        compression=1, new_subfile_type=0,
    )


def test_selects_only_tiles_intersecting_window_and_crops_edge():
    directory = make_directory()
    selected = select_tiff_tiles(
        directory, make_metadata(), RasterWindow(240, 250, 40, 50)
    )
    assert [(item.tile_row, item.tile_column) for item in selected] == [
        (0, 0), (0, 1), (1, 0), (1, 1)
    ]
    assert selected[0].window_row_offset == 240
    assert selected[0].window_column_offset == 250
    assert (selected[0].window_height, selected[0].window_width) == (16, 6)
    assert (selected[-1].window_height, selected[-1].window_width) == (24, 44)


def test_selects_partial_final_tile_at_raster_edge():
    selected = select_tiff_tiles(
        make_directory(), make_metadata(), RasterWindow(450, 550, 50, 50)
    )
    assert len(selected) == 1
    assert (selected[0].tile_height, selected[0].tile_width) == (244, 88)
    assert (selected[0].window_height, selected[0].window_width) == (50, 50)


def test_planar_separate_uses_band_major_block_order():
    directory = make_directory(bands=3, planar=2)
    selected = select_tiff_tiles(
        directory, make_metadata(bands=3), RasterWindow(0, 0, 10, 10, bands=(3, 1))
    )
    assert [item.band for item in selected] == [3, 1]
    assert [item.block_index for item in selected] == [8, 0]
    assert [item.byte_offset for item in selected] == [1800, 1000]


def test_chunky_layout_selects_tile_once_even_for_band_subset():
    selected = select_tiff_tiles(
        make_directory(bands=3), make_metadata(bands=3),
        RasterWindow(0, 0, 10, 10, bands=(2,))
    )
    assert len(selected) == 1
    assert selected[0].band == 0
    assert selected[0].block_index == 0


def test_rejects_out_of_bounds_windows_and_tile_budget():
    with pytest.raises(RasterContractError, match="beyond"):
        select_tiff_tiles(
            make_directory(), make_metadata(), RasterWindow(490, 590, 20, 20)
        )
    with pytest.raises(RasterContractError, match="selection limit"):
        select_tiff_tiles(
            make_directory(), make_metadata(), RasterWindow(240, 250, 40, 50),
            max_tiles=3,
        )


def test_rejects_inconsistent_tile_table():
    directory = make_directory()
    malformed = TiffDirectory(
        offset=directory.offset, width=directory.width, height=directory.height,
        tiled=directory.tiled, block_offsets=directory.block_offsets[:-1],
        block_byte_counts=directory.block_byte_counts[:-1],
        subifd_offsets=directory.subifd_offsets, next_ifd_offset=directory.next_ifd_offset,
        tile_width=directory.tile_width, tile_height=directory.tile_height,
        samples_per_pixel=directory.samples_per_pixel,
        planar_configuration=directory.planar_configuration,
        compression=directory.compression, new_subfile_type=directory.new_subfile_type,
    )
    with pytest.raises(RasterContractError, match="tile tables"):
        select_tiff_tiles(malformed, make_metadata(), RasterWindow(0, 0, 10, 10))
