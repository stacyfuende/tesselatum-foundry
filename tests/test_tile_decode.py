from __future__ import annotations

from dataclasses import replace
import struct
import zlib

import pytest

from tessellatum_foundry.sources import (
    DecodedRasterTile,
    RasterContractError,
    RasterMetadata,
    RasterTileSelection,
    TiffDirectory,
    decode_uncompressed_tiff_tile,
    decode_deflate_tiff_tile,
    decode_tiff_tile,
)


def metadata(*, dtypes=("uint8", "uint16"), width=18, height=10):
    return RasterMetadata(
        width=width,
        height=height,
        band_count=len(dtypes),
        dtypes=dtypes,
        transform=(0.0, 1.0, 0.0, 0.0, 0.0, -1.0),
    )


def directory(*, planar=1, compression=1, predictor=1, width=18, height=10):
    # Two tiles across, one down; each encoded tile is 16 x 16.
    planes = len(metadata().dtypes) if planar == 2 else 1
    offsets = tuple(100 + index * 1024 for index in range(2 * planes))
    if planar == 1:
        counts = (16 * 16 * 3, 16 * 16 * 3)
    else:
        counts = (16 * 16, 16 * 16 * 2, 16 * 16, 16 * 16 * 2)
    return TiffDirectory(
        offset=8, width=width, height=height, tiled=True,
        block_offsets=offsets, block_byte_counts=counts,
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=16, tile_height=16,
        samples_per_pixel=2, planar_configuration=planar,
        compression=compression, new_subfile_type=0, predictor=predictor,
    )


def selection(*, band=0, column=1, block=1, width=2, height=10, length=16 * 16 * 3):
    return RasterTileSelection(
        band=band, tile_row=0, tile_column=column, block_index=block,
        byte_offset=100 + block * 1024, byte_length=length,
        tile_row_offset=0, tile_column_offset=column * 16,
        tile_height=height, tile_width=width,
        window_row_offset=0, window_column_offset=column * 16,
        window_height=height, window_width=width,
    )


def test_decodes_uncompressed_chunky_samples_without_copy_or_rescaling():
    source = metadata()
    layout = directory()
    tile = selection()
    payload = bytes(16 * 16 * (1 + 2))

    result = decode_uncompressed_tiff_tile(
        payload, tile, layout, source, byte_order="little"
    )

    assert isinstance(result, DecodedRasterTile)
    assert result.samples is payload
    assert result.sample_dtypes == ("uint8", "uint16")
    assert result.sample_count == 16 * 16 * 2
    assert result.sample_bytes == len(payload)
    assert result.byte_order == "little"


def test_iter_pixels_unpacks_chunky_samples_in_source_byte_order():
    source = metadata()
    layout = directory()
    tile = selection()
    payload = struct.pack("<BH", 7, 513) * (16 * 16)
    result = decode_uncompressed_tiff_tile(
        payload, tile, layout, source, byte_order="little"
    )

    pixels = result.iter_pixels()
    assert next(pixels) == (7, 513)
    assert next(pixels) == (7, 513)


def test_iter_pixels_supports_big_endian_and_planar_samples():
    source = metadata()
    layout = directory(planar=2)
    tile = selection(band=2, block=3, length=16 * 16 * 2)
    payload = struct.pack(">H", 1025) * (16 * 16)
    result = decode_uncompressed_tiff_tile(
        payload, tile, layout, source, byte_order="big"
    )

    assert next(result.iter_pixels()) == (1025,)


def test_edge_tile_payload_still_uses_full_encoded_tile_dimensions():
    source = metadata()
    layout = directory()
    edge = selection(width=2, height=10)
    payload = bytes(16 * 16 * 3)

    result = decode_uncompressed_tiff_tile(
        payload, edge, layout, source, byte_order="big"
    )

    assert result.sample_bytes == 16 * 16 * 3
    assert result.byte_order == "big"


def test_planar_tile_decodes_only_selected_band():
    source = metadata()
    layout = directory(planar=2)
    tile = selection(band=2, block=3, length=16 * 16 * 2)
    payload = bytes(16 * 16 * 2)

    result = decode_uncompressed_tiff_tile(
        payload, tile, layout, source, byte_order="little"
    )

    assert result.sample_dtypes == ("uint16",)
    assert result.sample_count == 16 * 16
    assert result.sample_bytes == 16 * 16 * 2


@pytest.mark.parametrize(
    ("layout", "message"),
    [
        (directory(compression=8), "Only uncompressed"),
        (directory(predictor=2), "predictors are not supported"),
    ],
)
def test_rejects_compression_and_predictors(layout, message):
    with pytest.raises(RasterContractError, match=message):
        decode_uncompressed_tiff_tile(
            bytes(16 * 16 * 3), selection(), layout, metadata(), byte_order="little"
        )


def test_rejects_decoded_byte_and_pixel_budgets_before_returning_buffer():
    payload = bytes(16 * 16 * 3)
    with pytest.raises(RasterContractError, match="decoded byte limit"):
        decode_uncompressed_tiff_tile(
            payload, selection(), directory(), metadata(),
            byte_order="little", max_decoded_bytes=100,
        )
    with pytest.raises(RasterContractError, match="decoded pixel limit"):
        decode_uncompressed_tiff_tile(
            payload, selection(), directory(), metadata(),
            byte_order="little", max_pixels=100,
        )


def test_rejects_short_or_overlong_uncompressed_tile():
    with pytest.raises(RasterContractError, match="length does not match"):
        decode_uncompressed_tiff_tile(
            bytes(100), selection(), directory(), metadata(), byte_order="little"
        )
    with pytest.raises(RasterContractError, match="length does not match"):
        decode_uncompressed_tiff_tile(
            bytes(16 * 16 * 3 + 1), selection(), directory(), metadata(),
            byte_order="little",
        )


def test_rejects_selection_not_matching_directory_table():
    tile = selection()
    bad = replace(tile, byte_offset=tile.byte_offset + 1)
    with pytest.raises(RasterContractError, match="does not match"):
        decode_uncompressed_tiff_tile(
            bytes(16 * 16 * 3), bad, directory(), metadata(), byte_order="little"
        )


def test_rejects_packed_samples_and_invalid_byte_order():
    packed = metadata(dtypes=("uint1", "uint16"))
    with pytest.raises(RasterContractError, match="not byte-aligned"):
        decode_uncompressed_tiff_tile(
            bytes(16 * 16 * 3), selection(), directory(), packed, byte_order="little"
        )
    with pytest.raises(RasterContractError, match="byte order"):
        decode_uncompressed_tiff_tile(
            bytes(16 * 16 * 3), selection(), directory(), metadata(), byte_order="native"
        )

def compressed_fixture(raw):
    payload = zlib.compress(raw)
    layout = directory(compression=8)
    counts = list(layout.block_byte_counts)
    counts[1] = len(payload)
    layout = replace(layout, block_byte_counts=tuple(counts))
    tile = replace(selection(), byte_length=len(payload))
    return payload, tile, layout


def test_decodes_bounded_zlib_deflate_tile():
    raw = struct.pack("<BH", 9, 2049) * (16 * 16)
    payload, tile, layout = compressed_fixture(raw)

    result = decode_deflate_tiff_tile(
        payload, tile, layout, metadata(), byte_order="little"
    )

    assert result.sample_bytes == len(raw)
    assert next(result.iter_pixels()) == (9, 2049)


def test_deflate_decoder_rejects_expansion_beyond_output_budget():
    raw = bytes(16 * 16 * 3)
    payload, tile, layout = compressed_fixture(raw)

    with pytest.raises(RasterContractError, match="decoded byte limit"):
        decode_deflate_tiff_tile(
            payload, tile, layout, metadata(), byte_order="little",
            max_decoded_bytes=100,
        )


@pytest.mark.parametrize("suffix", [b"trailing", b""])
def test_deflate_decoder_rejects_trailing_or_truncated_stream(suffix):
    raw = bytes(16 * 16 * 3)
    payload, tile, layout = compressed_fixture(raw)
    if suffix:
        payload += suffix
        counts = list(layout.block_byte_counts)
        counts[1] = len(payload)
        layout = replace(layout, block_byte_counts=tuple(counts))
        tile = replace(tile, byte_length=len(payload))
    else:
        payload = payload[:-2]
        counts = list(layout.block_byte_counts)
        counts[1] = len(payload)
        layout = replace(layout, block_byte_counts=tuple(counts))
        tile = replace(tile, byte_length=len(payload))

    with pytest.raises(RasterContractError, match="incomplete|trailing"):
        decode_deflate_tiff_tile(
            payload, tile, layout, metadata(), byte_order="little"
        )


def test_deflate_decoder_enforces_compressed_input_budget():
    raw = bytes(16 * 16 * 3)
    payload, tile, layout = compressed_fixture(raw)

    with pytest.raises(RasterContractError, match="compressed TIFF tile"):
        decode_deflate_tiff_tile(
            payload, tile, layout, metadata(), byte_order="little",
            max_compressed_bytes=1,
        )


def test_deflate_decoder_rejects_predictors_and_unknown_compression():
    raw = bytes(16 * 16 * 3)
    payload, tile, layout = compressed_fixture(raw)
    unsupported_predictor = replace(layout, predictor=3)
    with pytest.raises(RasterContractError, match="Unsupported TIFF predictor"):
        decode_deflate_tiff_tile(
            payload, tile, unsupported_predictor, metadata(), byte_order="little"
        )
    unknown = replace(layout, compression=5)
    with pytest.raises(RasterContractError, match="Deflate compression"):
        decode_deflate_tiff_tile(
            payload, tile, unknown, metadata(), byte_order="little"
        )

def test_deflate_decoder_reverses_horizontal_predictor_for_chunky_integer_samples():
    encoded = bytearray()
    expected = []
    for row in range(16):
        previous = (0, 0)
        for column in range(16):
            current = (column + row, 1000 + column * 3 + row)
            delta = (
                (current[0] - previous[0]) % 256,
                (current[1] - previous[1]) % 65536,
            )
            encoded.extend(struct.pack("<BH", *delta))
            expected.append(current)
            previous = current
    payload, tile, layout = compressed_fixture(bytes(encoded))
    layout = replace(layout, predictor=2)

    result = decode_deflate_tiff_tile(
        payload, tile, layout, metadata(), byte_order="little"
    )

    pixels = list(result.iter_pixels())
    assert pixels == expected


def test_deflate_horizontal_predictor_rejects_floating_point_samples():
    raw = struct.pack("<fB", 1.0, 2) * (16 * 16)
    payload, tile, layout = compressed_fixture(raw)
    layout = replace(layout, predictor=2)
    float_metadata = metadata(dtypes=("float32", "uint8"))

    with pytest.raises(RasterContractError, match="only for integer"):
        decode_deflate_tiff_tile(
            payload, tile, layout, float_metadata, byte_order="little"
        )

def test_uncompressed_tiff_tile_decoder_reverses_horizontal_predictor():
    encoded = bytearray()
    expected = []
    for row in range(16):
        previous = (0, 0)
        for column in range(16):
            current = (column + row, 2000 + column * 2 + row)
            delta = (
                (current[0] - previous[0]) % 256,
                (current[1] - previous[1]) % 65536,
            )
            encoded.extend(struct.pack("<BH", *delta))
            expected.append(current)
            previous = current
    layout = replace(directory(), predictor=2)

    result = decode_tiff_tile(
        bytes(encoded), selection(), layout, metadata(), byte_order="little"
    )

    assert list(result.iter_pixels()) == expected


def test_unified_decoder_rejects_unsupported_compression():
    layout = replace(directory(), compression=5)
    with pytest.raises(RasterContractError, match="Unsupported TIFF tile compression"):
        decode_tiff_tile(
            bytes(16 * 16 * 3), selection(), layout, metadata(), byte_order="little"
        )

