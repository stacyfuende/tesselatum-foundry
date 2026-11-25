"""Bounded selection of TIFF tiles intersecting a raster pixel window."""
from __future__ import annotations

from dataclasses import dataclass

from .raster import RasterContractError, RasterMetadata, RasterWindow
from .tiff import TiffDirectory


@dataclass(frozen=True, slots=True)
class RasterTileSelection:
    """One TIFF tile range and the requested pixels covered within that tile."""

    band: int
    tile_row: int
    tile_column: int
    block_index: int
    byte_offset: int
    byte_length: int
    tile_row_offset: int
    tile_column_offset: int
    tile_height: int
    tile_width: int
    window_row_offset: int
    window_column_offset: int
    window_height: int
    window_width: int


def select_tiff_tiles(
    directory: TiffDirectory,
    metadata: RasterMetadata,
    window: RasterWindow,
    *,
    max_tiles: int = 256,
) -> tuple[RasterTileSelection, ...]:
    """Plan exact intersecting ranges; this does not decode tile payloads.

    Chunky images select each spatial tile once (band=0). Planar-separated
    images select a tile for each requested one-based band. Empty band
    selection means all bands. Edge tiles retain their full encoded range;
    intersection fields describe the requested pixels within each tile.
    """
    if isinstance(max_tiles, bool) or not isinstance(max_tiles, int) or max_tiles < 1:
        raise ValueError("max_tiles must be a positive integer.")
    if not directory.tiled or directory.tile_width is None or directory.tile_height is None:
        raise RasterContractError("Window tile selection requires a tiled TIFF directory.")
    if directory.width != metadata.width or directory.height != metadata.height:
        raise RasterContractError("TIFF directory dimensions do not match raster metadata.")
    if directory.samples_per_pixel != metadata.band_count:
        raise RasterContractError("TIFF samples-per-pixel does not match raster band count.")
    if directory.planar_configuration not in (1, 2):
        raise RasterContractError("Unsupported TIFF planar configuration.")
    metadata.validate_window(window)

    tile_width, tile_height = directory.tile_width, directory.tile_height
    across = (directory.width + tile_width - 1) // tile_width
    down = (directory.height + tile_height - 1) // tile_height
    tiles_per_plane = across * down
    planes = 1 if directory.planar_configuration == 1 else directory.samples_per_pixel
    expected = tiles_per_plane * planes
    if len(directory.block_offsets) != expected or len(directory.block_byte_counts) != expected:
        raise RasterContractError("TIFF tile tables do not match the declared tile grid.")
    bands = (0,) if directory.planar_configuration == 1 else (
        window.bands or tuple(range(1, metadata.band_count + 1))
    )
    first_col = window.column_offset // tile_width
    last_col = (window.column_offset + window.width - 1) // tile_width
    first_row = window.row_offset // tile_height
    last_row = (window.row_offset + window.height - 1) // tile_height
    count = (last_row - first_row + 1) * (last_col - first_col + 1) * len(bands)
    if count > max_tiles:
        raise RasterContractError("Raster window exceeds the configured tile selection limit.")

    selected = []
    for band in bands:
        plane = 0 if band == 0 else band - 1
        for tile_row in range(first_row, last_row + 1):
            for tile_column in range(first_col, last_col + 1):
                spatial_index = tile_row * across + tile_column
                block_index = plane * tiles_per_plane + spatial_index
                top, left = tile_row * tile_height, tile_column * tile_width
                bottom = min(window.row_offset + window.height, top + tile_height, directory.height)
                right = min(window.column_offset + window.width, left + tile_width, directory.width)
                offset = directory.block_offsets[block_index]
                length = directory.block_byte_counts[block_index]
                if (
                    isinstance(offset, bool) or not isinstance(offset, int) or offset < 0
                    or isinstance(length, bool) or not isinstance(length, int) or length < 1
                ):
                    raise RasterContractError("TIFF tile byte range is invalid.")
                selected.append(RasterTileSelection(
                    band, tile_row, tile_column, block_index, offset, length, top, left,
                    min(tile_height, directory.height - top),
                    min(tile_width, directory.width - left),
                    max(window.row_offset, top), max(window.column_offset, left),
                    bottom - max(window.row_offset, top),
                    right - max(window.column_offset, left),
                ))
    return tuple(selected)
