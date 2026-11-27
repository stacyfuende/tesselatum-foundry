"""End-to-end bounded TIFF window reads, including concrete overview selection."""
from __future__ import annotations

from dataclasses import dataclass

from .overview_selection import SelectedTiffOverview, select_tiff_overview
from .raster import RasterWindow
from .tile_decode import decode_tiff_tile
from .tile_reads import read_selected_tiff_tiles
from .tile_selection import select_tiff_tiles
from .tiff import TiffRangeReader
from .window_assembly import RasterWindowBuffer, assemble_tiff_window


@dataclass(frozen=True, slots=True)
class TiffWindowRead:
    """A raster window and the exact TIFF directory/grid used to produce it."""

    overview: SelectedTiffOverview
    buffer: RasterWindowBuffer


def read_tiff_window(
    reader: TiffRangeReader,
    *,
    file_size: int,
    window: RasterWindow,
    target_downsample: float = 1,
    max_directories: int = 256,
    max_tiles: int = 256,
    max_output_bytes: int = 256 * 1024 * 1024,
    max_compressed_bytes: int = 16 * 1024 * 1024,
    max_decoded_bytes: int = 64 * 1024 * 1024,
    max_pixels_per_tile: int = 16 * 1024 * 1024,
) -> TiffWindowRead:
    """Read one window from a selected base/overview IFD under shared budgets.

    The requested window is expressed in pixel coordinates on the selected
    directory's grid. The target downsample is caller supplied; this function
    does not infer a destination grid or perform reprojection/resampling.
    Metadata and tile payloads are read through the same ETag-pinned,
    cumulative-budget range reader owned by TiffRangeReader.
    """
    directories = reader.read_directory_index(
        file_size=file_size,
        max_directories=max_directories,
    )
    base = reader.read(file_size=file_size)
    selected = select_tiff_overview(
        directories,
        base.metadata,
        target_downsample=target_downsample,
    )
    selections = select_tiff_tiles(
        selected.directory,
        selected.metadata,
        window,
        max_tiles=max_tiles,
    )

    def decoded_tiles():
        for retrieved in read_selected_tiff_tiles(reader.source, selections):
            yield decode_tiff_tile(
                retrieved.payload,
                retrieved.selection,
                selected.directory,
                selected.metadata,
                byte_order=base.layout.byte_order,
                max_compressed_bytes=max_compressed_bytes,
                max_decoded_bytes=max_decoded_bytes,
                max_pixels=max_pixels_per_tile,
            )

    buffer = assemble_tiff_window(
        decoded_tiles(),
        selected.directory,
        selected.metadata,
        window,
        byte_order=base.layout.byte_order,
        max_output_bytes=max_output_bytes,
        max_tiles=max_tiles,
    )
    return TiffWindowRead(overview=selected, buffer=buffer)
