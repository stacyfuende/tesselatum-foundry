"""Bounded assembly of decoded TIFF tiles into a requested raster window."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .raster import RasterContractError, RasterMetadata, RasterWindow
from .tile_decode import DecodedRasterTile, _DTYPE_BYTES
from .tile_selection import select_tiff_tiles
from .tiff import TiffDirectory


@dataclass(frozen=True, slots=True)
class RasterWindowBuffer:
    """Pixel-interleaved raw samples for one requested window.

    The output contains only selected bands, in RasterWindow.bands order (or
    source band order when no subset is supplied). Samples retain TIFF byte
    order and numeric dtype; no rescaling or color conversion is performed.
    """

    window: RasterWindow
    bands: tuple[int, ...]
    dtypes: tuple[str, ...]
    byte_order: str
    samples: bytes

    @property
    def byte_length(self) -> int:
        return len(self.samples)


def assemble_tiff_window(
    tiles: Iterable[DecodedRasterTile],
    directory: TiffDirectory,
    metadata: RasterMetadata,
    window: RasterWindow,
    *,
    byte_order: str,
    max_output_bytes: int = 256 * 1024 * 1024,
    max_tiles: int = 256,
) -> RasterWindowBuffer:
    """Assemble an exact, bounded set of decoded tiles into a pixel window.

    Tiles must arrive in the same deterministic order as select_tiff_tiles.
    The assembler allocates only the final output buffer and copies each
    intersection before requesting the next item from the iterable.
    """
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int):
        raise ValueError("max_output_bytes must be a positive integer.")
    if max_output_bytes < 1:
        raise ValueError("max_output_bytes must be a positive integer.")
    if byte_order not in ("little", "big"):
        raise RasterContractError("Raster window byte order must be 'little' or 'big'.")

    selections = select_tiff_tiles(directory, metadata, window, max_tiles=max_tiles)
    bands = window.bands or tuple(range(1, metadata.band_count + 1))
    dtypes = tuple(metadata.dtypes[band - 1] for band in bands)
    try:
        source_widths = tuple(_DTYPE_BYTES[dtype] for dtype in metadata.dtypes)
        output_widths = tuple(_DTYPE_BYTES[dtype] for dtype in dtypes)
    except KeyError as error:
        raise RasterContractError("Raster window contains an unsupported sample dtype.") from error

    source_pixel_bytes = sum(source_widths)
    output_pixel_bytes = sum(output_widths)
    output_size = window.width * window.height * output_pixel_bytes
    if output_size > max_output_bytes:
        raise RasterContractError("Raster window exceeds the configured output byte limit.")

    output = bytearray(output_size)
    output_band_offsets = []
    offset = 0
    for width in output_widths:
        output_band_offsets.append(offset)
        offset += width

    expected_count = len(selections)
    iterator = iter(tiles)
    for index, expected in enumerate(selections):
        try:
            tile = next(iterator)
        except StopIteration as error:
            raise RasterContractError("Raster window is missing one or more decoded tiles.") from error
        if not isinstance(tile, DecodedRasterTile) or tile.selection != expected:
            raise RasterContractError("Decoded tiles are duplicated, missing, or out of order.")
        if tile.byte_order != byte_order:
            raise RasterContractError("Decoded tile byte order does not match the window.")
        expected_dtypes = (
            metadata.dtypes if directory.planar_configuration == 1
            else (metadata.dtypes[expected.band - 1],)
        )
        if tile.sample_dtypes != expected_dtypes:
            raise RasterContractError("Decoded tile sample dtypes do not match the source layout.")
        expected_tile_bytes = (
            directory.tile_width * directory.tile_height
            * sum(_DTYPE_BYTES[dtype] for dtype in expected_dtypes)
        )
        if len(tile.samples) != expected_tile_bytes or tile.sample_bytes != expected_tile_bytes:
            raise RasterContractError("Decoded tile buffer length does not match its TIFF tile grid.")

        source_row = expected.window_row_offset - expected.tile_row_offset
        source_col = expected.window_column_offset - expected.tile_column_offset
        dest_row = expected.window_row_offset - window.row_offset
        dest_col = expected.window_column_offset - window.column_offset

        for row in range(expected.window_height):
            for col in range(expected.window_width):
                src_pixel = (
                    (source_row + row) * directory.tile_width + source_col + col
                )
                dst_pixel = (
                    (dest_row + row) * window.width + dest_col + col
                )
                if directory.planar_configuration == 1:
                    for output_band_index, band in enumerate(bands):
                        source_offset = src_pixel * source_pixel_bytes + sum(
                            source_widths[: band - 1]
                        )
                        target_offset = dst_pixel * output_pixel_bytes + output_band_offsets[
                            output_band_index
                        ]
                        width = output_widths[output_band_index]
                        output[target_offset : target_offset + width] = (
                            tile.samples[source_offset : source_offset + width]
                        )
                else:
                    band_index = expected.band - 1
                    output_band_index = bands.index(expected.band)
                    width = output_widths[output_band_index]
                    source_offset = src_pixel * width
                    target_offset = (
                        dst_pixel * output_pixel_bytes + output_band_offsets[output_band_index]
                    )
                    output[target_offset : target_offset + width] = (
                        tile.samples[source_offset : source_offset + width]
                    )

    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise RasterContractError("Raster window received unexpected extra decoded tiles.")

    if index + 1 != expected_count:
        raise RasterContractError("Raster window tile coverage is incomplete.")
    return RasterWindowBuffer(
        window=window,
        bands=bands,
        dtypes=dtypes,
        byte_order=byte_order,
        samples=bytes(output),
    )
