"""Strict, bounded extraction of uncompressed TIFF tile sample buffers.

This first decoder intentionally supports only byte-aligned, uncompressed,
predictor-free samples. It does not decompress, rescale, color-convert, or
assemble windows.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from struct import unpack_from
from collections.abc import Iterator
import zlib

from .raster import RasterContractError, RasterMetadata
from .tile_selection import RasterTileSelection
from .tiff import TiffDirectory


@dataclass(frozen=True, slots=True)
class DecodedRasterTile:
    """A validated raw sample buffer with its numeric interpretation metadata.

    Samples remain in the TIFF's declared byte order. Chunky buffers are
    pixel-interleaved; planar buffers contain the selected band only.
    """

    selection: RasterTileSelection
    samples: bytes | bytearray
    byte_order: str
    sample_dtypes: tuple[str, ...]
    sample_count: int
    sample_bytes: int

    def iter_pixels(self) -> Iterator[tuple[int | float, ...]]:
        """Yield one pixel at a time without materializing a decoded array."""
        formats = {
            "uint8": "B", "int8": "b",
            "uint16": "H", "int16": "h",
            "uint32": "I", "int32": "i", "float32": "f",
            "uint64": "Q", "int64": "q", "float64": "d",
        }
        prefix = "<" if self.byte_order == "little" else ">"
        widths = tuple(_DTYPE_BYTES[dtype] for dtype in self.sample_dtypes)
        pixel_count = self.sample_count // len(self.sample_dtypes)
        offset = 0
        for _ in range(pixel_count):
            values = []
            for dtype, width in zip(self.sample_dtypes, widths):
                values.append(unpack_from(prefix + formats[dtype], self.samples, offset)[0])
                offset += width
            yield tuple(values)


_DTYPE_BYTES = {
    "uint8": 1, "int8": 1,
    "uint16": 2, "int16": 2,
    "uint32": 4, "int32": 4, "float32": 4,
    "uint64": 8, "int64": 8, "float64": 8,
}


def decode_uncompressed_tiff_tile(
    payload: bytes | bytearray,
    selection: RasterTileSelection,
    directory: TiffDirectory,
    metadata: RasterMetadata,
    *,
    byte_order: str,
    max_decoded_bytes: int = 64 * 1024 * 1024,
    max_pixels: int = 16 * 1024 * 1024,
) -> DecodedRasterTile:
    """Validate and expose one uncompressed tile's bounded numeric samples.

    TIFF tiles encode the full tile dimensions, including padding beyond the
    image edge. No decompression is performed. Unsupported compression,
    horizontal/floating-point predictors, packed samples, and unsupported
    dtypes fail closed.
    """
    for name, value in (
        ("max_decoded_bytes", max_decoded_bytes),
        ("max_pixels", max_pixels),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if byte_order not in ("little", "big"):
        raise RasterContractError("TIFF byte order must be 'little' or 'big'.")
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("TIFF tile payload must be bytes or bytearray.")
    if not directory.tiled or directory.tile_width is None or directory.tile_height is None:
        raise RasterContractError("Tile decoding requires a tiled TIFF directory.")
    if directory.compression != 1:
        raise RasterContractError("Only uncompressed TIFF tiles are currently supported.")
    if directory.predictor != 1:
        raise RasterContractError("TIFF predictors are not supported by this decoder.")
    if directory.planar_configuration not in (1, 2):
        raise RasterContractError("Unsupported TIFF planar configuration.")
    if directory.samples_per_pixel != metadata.band_count:
        raise RasterContractError("TIFF samples-per-pixel does not match raster metadata.")
    if len(directory.block_offsets) != len(directory.block_byte_counts):
        raise RasterContractError("TIFF tile offset and byte-count tables do not align.")
    if (
        isinstance(selection.block_index, bool)
        or not isinstance(selection.block_index, int)
        or selection.block_index < 0
        or selection.block_index >= len(directory.block_offsets)
    ):
        raise RasterContractError("Selected TIFF tile index is outside the tile table.")
    if (
        directory.block_offsets[selection.block_index] != selection.byte_offset
        or directory.block_byte_counts[selection.block_index] != selection.byte_length
    ):
        raise RasterContractError("Tile selection does not match the TIFF directory table.")
    across = (directory.width + directory.tile_width - 1) // directory.tile_width
    down = (directory.height + directory.tile_height - 1) // directory.tile_height
    if (
        isinstance(selection.tile_row, bool)
        or not isinstance(selection.tile_row, int)
        or isinstance(selection.tile_column, bool)
        or not isinstance(selection.tile_column, int)
        or not 0 <= selection.tile_row < down
        or not 0 <= selection.tile_column < across
    ):
        raise RasterContractError("Selected TIFF tile coordinates are outside the tile grid.")
    expected_selection_width = min(
        directory.tile_width,
        directory.width - selection.tile_column * directory.tile_width,
    )
    expected_selection_height = min(
        directory.tile_height,
        directory.height - selection.tile_row * directory.tile_height,
    )
    if (
        selection.tile_width != expected_selection_width
        or selection.tile_height != expected_selection_height
        or expected_selection_width < 1
        or expected_selection_height < 1
    ):
        raise RasterContractError("Selected tile dimensions do not match the TIFF directory grid.")
    if selection.band == 0:
        if directory.planar_configuration != 1:
            raise RasterContractError("A planar TIFF tile must identify its one-based band.")
        dtypes = metadata.dtypes
    else:
        if directory.planar_configuration != 2:
            raise RasterContractError("A chunky TIFF tile must use band zero.")
        if not 1 <= selection.band <= metadata.band_count:
            raise RasterContractError("Selected TIFF band is outside the raster band range.")
        dtypes = (metadata.dtypes[selection.band - 1],)

    try:
        sample_widths = tuple(_DTYPE_BYTES[dtype] for dtype in dtypes)
    except KeyError as error:
        message = "TIFF sample dtype is unsupported or not byte-aligned."
        raise RasterContractError(message) from error

    pixels = directory.tile_width * directory.tile_height
    if pixels > max_pixels:
        raise RasterContractError("TIFF tile exceeds the configured decoded pixel limit.")
    bytes_per_pixel = sum(sample_widths)
    expected_bytes = pixels * bytes_per_pixel
    if expected_bytes > max_decoded_bytes:
        raise RasterContractError("TIFF tile exceeds the configured decoded byte limit.")
    if selection.byte_length != expected_bytes or len(payload) != expected_bytes:
        raise RasterContractError("Uncompressed TIFF tile length does not match its sample layout.")

    return DecodedRasterTile(
        selection=selection,
        samples=payload,
        byte_order=byte_order,
        sample_dtypes=dtypes,
        sample_count=pixels * len(dtypes),
        sample_bytes=expected_bytes,
    )

def decode_deflate_tiff_tile(
    payload: bytes,
    selection: RasterTileSelection,
    directory: TiffDirectory,
    metadata: RasterMetadata,
    *,
    byte_order: str,
    max_compressed_bytes: int = 16 * 1024 * 1024,
    max_decoded_bytes: int = 64 * 1024 * 1024,
    max_pixels: int = 16 * 1024 * 1024,
) -> DecodedRasterTile:
    """Decode one TIFF Deflate tile with a hard output cap.

    Supports TIFF Compression=8 and the legacy Deflate code 32946, using the
    zlib-wrapped Deflate stream. Predictor reversal is deliberately unsupported.
    """
    for name, value in (
        ("max_compressed_bytes", max_compressed_bytes),
        ("max_decoded_bytes", max_decoded_bytes),
        ("max_pixels", max_pixels),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if not isinstance(payload, bytes):
        raise TypeError("TIFF tile payload must be bytes.")
    if directory.compression not in (8, 32946):
        raise RasterContractError("TIFF tile does not use a supported Deflate compression code.")
    if directory.predictor not in (1, 2):
        raise RasterContractError("Unsupported TIFF predictor for Deflate tile decoding.")
    if len(payload) > max_compressed_bytes:
        raise RasterContractError("Compressed TIFF tile exceeds the configured byte limit.")
    if (
        isinstance(selection.block_index, bool)
        or not isinstance(selection.block_index, int)
        or not 0 <= selection.block_index < len(directory.block_byte_counts)
        or directory.block_byte_counts[selection.block_index] != len(payload)
        or selection.byte_length != len(payload)
    ):
        message = "Compressed tile payload does not match its directory byte count."
        raise RasterContractError(message)
    if directory.tile_width is None or directory.tile_height is None:
        raise RasterContractError("Deflate decoding requires a tiled TIFF directory.")
    if selection.band == 0 and directory.planar_configuration == 1:
        dtypes = metadata.dtypes
    elif (
        directory.planar_configuration == 2
        and 1 <= selection.band <= metadata.band_count
    ):
        dtypes = (metadata.dtypes[selection.band - 1],)
    else:
        raise RasterContractError("Selected TIFF tile band does not match planar configuration.")
    try:
        bytes_per_pixel = sum(_DTYPE_BYTES[dtype] for dtype in dtypes)
    except KeyError as error:
        message = "TIFF sample dtype is unsupported or not byte-aligned."
        raise RasterContractError(message) from error
    pixels = directory.tile_width * directory.tile_height
    if pixels > max_pixels:
        raise RasterContractError("TIFF tile exceeds the configured decoded pixel limit.")
    expected_bytes = pixels * bytes_per_pixel
    if expected_bytes > max_decoded_bytes:
        raise RasterContractError("TIFF tile exceeds the configured decoded byte limit.")

    decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS)
    try:
        decoded = decompressor.decompress(payload, expected_bytes + 1)
    except zlib.error as error:
        raise RasterContractError("TIFF Deflate tile is malformed.") from error
    if (
        len(decoded) != expected_bytes
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        raise RasterContractError(
            "TIFF Deflate stream is incomplete, has trailing data, or violates its decoded size."
        )

    if directory.predictor == 2:
        decoded = _undo_horizontal_predictor(
            decoded,
            tile_width=directory.tile_width,
            tile_height=directory.tile_height,
            sample_dtypes=dtypes,
            byte_order=byte_order,
        )
    decoded_directory = replace(
        directory,
        compression=1,
        predictor=1,
        block_byte_counts=tuple(
            expected_bytes if index == selection.block_index else count
            for index, count in enumerate(directory.block_byte_counts)
        ),
    )
    decoded_selection = replace(selection, byte_length=expected_bytes)
    return decode_uncompressed_tiff_tile(
        decoded,
        decoded_selection,
        decoded_directory,
        metadata,
        byte_order=byte_order,
        max_decoded_bytes=max_decoded_bytes,
        max_pixels=max_pixels,
    )


def _undo_horizontal_predictor(
    samples: bytes,
    *,
    tile_width: int,
    tile_height: int,
    sample_dtypes: tuple[str, ...],
    byte_order: str,
) -> bytearray:
    """Reverse TIFF Predictor=2 in-place on one bounded mutable tile buffer."""
    if any(dtype.startswith("float") for dtype in sample_dtypes):
        raise RasterContractError("Horizontal predictor is supported only for integer samples.")
    widths = tuple(_DTYPE_BYTES[dtype] for dtype in sample_dtypes)
    bits = tuple(width * 8 for width in widths)
    pixel_stride = sum(widths)
    row_stride = tile_width * pixel_stride
    output = bytearray(samples)
    for row in range(tile_height):
        row_start = row * row_stride
        for column in range(1, tile_width):
            pixel_start = row_start + column * pixel_stride
            previous_start = pixel_start - pixel_stride
            for sample_width, sample_bits, channel_offset in zip(
                widths, bits, _sample_offsets(widths)
            ):
                current = pixel_start + channel_offset
                previous = previous_start + channel_offset
                encoded = int.from_bytes(
                    output[current:current + sample_width], byte_order
                )
                prior = int.from_bytes(
                    output[previous:previous + sample_width], byte_order
                )
                value = (encoded + prior) % (1 << sample_bits)
                output[current:current + sample_width] = value.to_bytes(
                    sample_width, byte_order
                )
    return output


def _sample_offsets(widths: tuple[int, ...]) -> tuple[int, ...]:
    offsets = []
    offset = 0
    for width in widths:
        offsets.append(offset)
        offset += width
    return tuple(offsets)

def decode_tiff_tile(
    payload: bytes,
    selection: RasterTileSelection,
    directory: TiffDirectory,
    metadata: RasterMetadata,
    *,
    byte_order: str,
    max_compressed_bytes: int = 16 * 1024 * 1024,
    max_decoded_bytes: int = 64 * 1024 * 1024,
    max_pixels: int = 16 * 1024 * 1024,
) -> DecodedRasterTile:
    """Decode one supported TIFF tile using explicit compression/predictor gates."""
    if directory.compression in (8, 32946):
        return decode_deflate_tiff_tile(
            payload,
            selection,
            directory,
            metadata,
            byte_order=byte_order,
            max_compressed_bytes=max_compressed_bytes,
            max_decoded_bytes=max_decoded_bytes,
            max_pixels=max_pixels,
        )
    if directory.compression != 1:
        raise RasterContractError("Unsupported TIFF tile compression.")
    if directory.predictor == 1:
        return decode_uncompressed_tiff_tile(
            payload,
            selection,
            directory,
            metadata,
            byte_order=byte_order,
            max_decoded_bytes=max_decoded_bytes,
            max_pixels=max_pixels,
        )
    if directory.predictor != 2:
        raise RasterContractError("Unsupported TIFF predictor.")
    validated = decode_uncompressed_tiff_tile(
        payload,
        selection,
        replace(directory, predictor=1),
        metadata,
        byte_order=byte_order,
        max_decoded_bytes=max_decoded_bytes,
        max_pixels=max_pixels,
    )
    samples = _undo_horizontal_predictor(
        validated.samples,
        tile_width=directory.tile_width,
        tile_height=directory.tile_height,
        sample_dtypes=validated.sample_dtypes,
        byte_order=byte_order,
    )
    return replace(validated, samples=samples)

