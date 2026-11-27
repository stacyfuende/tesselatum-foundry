from __future__ import annotations

from dataclasses import replace

import pytest

from tessellatum_foundry.sources import (
    DecodedRasterTile,
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    TiffDirectory,
    assemble_tiff_window,
    select_tiff_tiles,
)


def metadata():
    return RasterMetadata(
        width=4, height=4, band_count=2, dtypes=("uint8", "uint8"),
        transform=(0, 1, 0, 0, 0, -1),
    )


def directory(*, planar=1):
    count = 4 if planar == 1 else 8
    return TiffDirectory(
        offset=8, width=4, height=4, tiled=True,
        block_offsets=tuple(100 + i * 4 for i in range(count)),
        block_byte_counts=(4,) * count,
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=2, tile_height=2, samples_per_pixel=2,
        planar_configuration=planar, compression=1, new_subfile_type=0,
        predictor=1,
    )


def decoded_tiles(layout, window, *, byte_order="little"):
    source = metadata()
    selections = select_tiff_tiles(layout, source, window)
    result = []
    for selection in selections:
        samples = bytearray()
        if layout.planar_configuration == 1:
            for row in range(2):
                for col in range(2):
                    y = selection.tile_row_offset + row
                    x = selection.tile_column_offset + col
                    samples.extend((y * 10 + x, 100 + y * 10 + x))
            dtypes = source.dtypes
            count = 8
        else:
            band = selection.band
            for row in range(2):
                for col in range(2):
                    y = selection.tile_row_offset + row
                    x = selection.tile_column_offset + col
                    value = y * 10 + x + (100 if band == 2 else 0)
                    samples.append(value)
            dtypes = (source.dtypes[band - 1],)
            count = 4
        result.append(DecodedRasterTile(
            selection=selection, samples=bytes(samples), byte_order=byte_order,
            sample_dtypes=dtypes, sample_count=count, sample_bytes=len(samples),
        ))
    return result


def test_assembles_chunky_window_across_four_tiles_in_pixel_interleaved_order():
    layout = directory()
    window = RasterWindow(1, 1, 3, 3)

    result = assemble_tiff_window(
        decoded_tiles(layout, window), layout, metadata(), window, byte_order="little"
    )

    assert result.bands == (1, 2)
    assert result.dtypes == ("uint8", "uint8")
    assert list(result.samples) == [
        11, 111, 12, 112, 13, 113,
        21, 121, 22, 122, 23, 123,
        31, 131, 32, 132, 33, 133,
    ]


def test_assembles_planar_bands_and_preserves_requested_band_order():
    layout = directory(planar=2)
    window = RasterWindow(1, 1, 2, 2, bands=(2, 1))

    result = assemble_tiff_window(
        decoded_tiles(layout, window), layout, metadata(), window, byte_order="little"
    )

    assert result.bands == (2, 1)
    assert list(result.samples) == [
        111, 11, 112, 12,
        121, 21, 122, 22,
    ]


def test_chunky_band_subset_is_extracted_in_requested_order():
    layout = directory()
    window = RasterWindow(0, 0, 2, 2, bands=(2,))

    result = assemble_tiff_window(
        decoded_tiles(layout, window), layout, metadata(), window, byte_order="little"
    )

    assert result.bands == (2,)
    assert list(result.samples) == [100, 101, 110, 111]


def test_rejects_missing_duplicate_out_of_order_and_extra_tiles():
    layout = directory()
    window = RasterWindow(0, 0, 4, 4)
    tiles = decoded_tiles(layout, window)

    with pytest.raises(RasterContractError, match="missing"):
        assemble_tiff_window(tiles[:-1], layout, metadata(), window, byte_order="little")
    with pytest.raises(RasterContractError, match="duplicated, missing, or out of order"):
        assemble_tiff_window(
            [tiles[0], tiles[0], *tiles[2:]], layout, metadata(), window,
            byte_order="little",
        )
    with pytest.raises(RasterContractError, match="extra"):
        assemble_tiff_window(
            [*tiles, tiles[-1]], layout, metadata(), window, byte_order="little"
        )


def test_rejects_mismatched_dtype_byte_order_and_output_budget():
    layout = directory()
    window = RasterWindow(0, 0, 2, 2)
    tiles = decoded_tiles(layout, window)

    with pytest.raises(RasterContractError, match="byte order"):
        assemble_tiff_window(tiles, layout, metadata(), window, byte_order="big")
    with pytest.raises(RasterContractError, match="sample dtypes"):
        assemble_tiff_window(
            [replace(tiles[0], sample_dtypes=("uint16", "uint8")), *tiles[1:]],
            layout, metadata(), window, byte_order="little",
        )
    with pytest.raises(RasterContractError, match="output byte limit"):
        assemble_tiff_window(
            tiles, layout, metadata(), window, byte_order="little", max_output_bytes=3
        )
