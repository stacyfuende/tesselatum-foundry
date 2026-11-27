"""Strict, bounded extraction of uncompressed TIFF tile sample buffers.

This first decoder intentionally supports only byte-aligned, uncompressed,
predictor-free samples. It does not decompress, rescale, color-convert, or
assemble windows.
"""
from __future__ import annotations

from dataclasses import dataclass
from struct import unpack_from
from collections.abc import Iterator

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
    samples: bytes
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
    payload: bytes,
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
    if not isinstance(payload, bytes):
        raise TypeError("TIFF tile payload must be bytes.")
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
        raise RasterContractError("TIFF sample dtype is unsupported or not byte-aligned.") from error

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
