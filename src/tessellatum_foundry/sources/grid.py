"""Same-CRS destination-grid planning and bounded raster resampling."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace

from .nodata import window_validity_mask
from .raster import RasterContractError, RasterMetadata, RasterWindow
from .window_assembly import RasterWindowBuffer


@dataclass(frozen=True, slots=True)
class RasterResampleResult:
    """Resampled single-band float64 pixels, output metadata and validity."""

    buffer: RasterWindowBuffer
    metadata: RasterMetadata
    valid: tuple[bool, ...]


def _finite_positive(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RasterContractError(f"{name} must be a finite positive number.")
    return float(value)


def _snap_index(value: float, *, upper: bool) -> int:
    nearest = round(value)
    if math.isclose(value, nearest, rel_tol=1e-12, abs_tol=1e-12):
        return int(nearest)
    return math.ceil(value) if upper else math.floor(value)


def _north_up(metadata: RasterMetadata) -> None:
    x_origin, pixel_width, row_rotation, y_origin, column_rotation, pixel_height = (
        metadata.transform
    )
    if (
        row_rotation != 0
        or column_rotation != 0
        or pixel_width <= 0
        or pixel_height >= 0
    ):
        raise RasterContractError(
            "This raster grid operation currently requires north-up, unrotated grids."
        )
    if metadata.crs is None:
        raise RasterContractError("Destination-grid planning requires an explicit CRS.")


def plan_destination_grid(
    source: RasterMetadata,
    *,
    pixel_width: float,
    pixel_height: float,
    anchor_x: float = 0,
    anchor_y: float = 0,
    max_pixels: int = 100_000_000,
) -> RasterMetadata:
    """Plan an outward-snapped north-up grid in the source CRS.

    This deliberately does not transform coordinates. The output covers the
    complete source extent, aligned to the supplied anchor and positive pixel
    resolutions. Rotated grids and unknown CRSs fail closed.
    """
    resolution_x = _finite_positive(pixel_width, "pixel_width")
    resolution_y = _finite_positive(pixel_height, "pixel_height")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in (anchor_x, anchor_y)
    ):
        raise RasterContractError("Grid anchors must be finite numbers.")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or max_pixels < 1:
        raise RasterContractError("max_pixels must be a positive integer.")
    _north_up(source)
    origin_x, source_px, _, origin_y, _, source_py = source.transform
    min_x = origin_x
    max_x = origin_x + source.width * source_px
    max_y = origin_y
    min_y = origin_y + source.height * source_py
    left_index = _snap_index((min_x - anchor_x) / resolution_x, upper=False)
    right_index = _snap_index((max_x - anchor_x) / resolution_x, upper=True)
    bottom_index = _snap_index((min_y - anchor_y) / resolution_y, upper=False)
    top_index = _snap_index((max_y - anchor_y) / resolution_y, upper=True)
    left = anchor_x + left_index * resolution_x
    right = anchor_x + right_index * resolution_x
    bottom = anchor_y + bottom_index * resolution_y
    top = anchor_y + top_index * resolution_y
    width = right_index - left_index
    height = top_index - bottom_index
    if width < 1 or height < 1 or width * height > max_pixels:
        raise RasterContractError("Planned destination grid exceeds its pixel budget.")
    return RasterMetadata(
        width=width,
        height=height,
        band_count=source.band_count,
        dtypes=source.dtypes,
        transform=(left, resolution_x, 0, top, 0, -resolution_y),
        crs=source.crs,
        nodata=source.nodata,
        driver="FoundryGrid",
        metadata={"grid_plan": "same_crs_outward_snap"},
    )


def resample_raster_window(
    source: RasterWindowBuffer,
    source_metadata: RasterMetadata,
    destination: RasterMetadata,
    *,
    method: str = "nearest",
    max_output_bytes: int = 256 * 1024 * 1024,
) -> RasterResampleResult:
    """Resample a covered single-band source window onto a same-CRS grid.

    Nearest-neighbour uses the closest source pixel centre. Bilinear requires
    all four neighbouring samples to be in-bounds and valid; it does not
    renormalize around NoData. Pixels outside the source extent are invalid.
    A source buffer that omits a required in-bounds sample is rejected rather
    than silently producing a partial result.
    """
    if method not in ("nearest", "bilinear"):
        raise RasterContractError("Resampling method must be 'nearest' or 'bilinear'.")
    if source_metadata.band_count != 1 or len(source.bands) != 1:
        raise RasterContractError("Raster resampling currently requires one selected band.")
    if destination.band_count != 1:
        raise RasterContractError("Destination grid must contain exactly one band.")
    if source_metadata.crs != destination.crs or source_metadata.crs is None:
        raise RasterContractError("Raster resampling requires an identical, explicit CRS.")
    _north_up(source_metadata)
    _north_up(destination)
    source.window.validate_against(source_metadata)
    if source.bands != (1,) or source.dtypes != (source_metadata.dtypes[0],):
        raise RasterContractError("Source raster buffer does not match its metadata.")
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes < 1:
        raise RasterContractError("max_output_bytes must be a positive integer.")
    output_size = destination.width * destination.height * 8
    if output_size > max_output_bytes:
        raise RasterContractError("Resampled output exceeds the configured byte limit.")

    formats = {
        "uint8": "B", "int8": "b", "uint16": "H", "int16": "h",
        "uint32": "I", "int32": "i", "uint64": "Q", "int64": "q",
        "float32": "f", "float64": "d",
    }
    dtype = source.dtypes[0]
    if dtype not in formats:
        raise RasterContractError("Unsupported source dtype for raster resampling.")
    source_prefix = "<" if source.byte_order == "little" else ">"
    source_format = source_prefix + formats[dtype]
    source_width = struct.calcsize(source_format)
    validity = window_validity_mask(source, source_metadata)
    source_px = source_metadata.transform[1]
    source_py = source_metadata.transform[5]
    source_x0 = source_metadata.transform[0]
    source_y0 = source_metadata.transform[3]
    dest_x0, dest_px, _, dest_y0, _, dest_py = destination.transform
    output = bytearray()
    output_valid = []

    def sample(row: int, col: int) -> tuple[float, bool]:
        if row < 0 or col < 0 or row >= source_metadata.height or col >= source_metadata.width:
            return 0.0, False
        local_row = row - source.window.row_offset
        local_col = col - source.window.column_offset
        if (
            local_row < 0
            or local_col < 0
            or local_row >= source.window.height
            or local_col >= source.window.width
        ):
            raise RasterContractError(
                "Source window does not cover every in-bounds resampling sample."
            )
        index = local_row * source.window.width + local_col
        value = struct.unpack_from(
            source_format, source.samples, index * source_width
        )[0]
        return float(value), validity[index] and math.isfinite(value)

    for out_row in range(destination.height):
        world_y = dest_y0 + (out_row + 0.5) * dest_py
        source_row_center = (world_y - source_y0) / source_py - 0.5
        for out_col in range(destination.width):
            world_x = dest_x0 + (out_col + 0.5) * dest_px
            source_col_center = (world_x - source_x0) / source_px - 0.5
            if method == "nearest":
                row = math.floor(source_row_center + 0.5)
                col = math.floor(source_col_center + 0.5)
                value, valid = sample(row, col)
            else:
                row0 = math.floor(source_row_center)
                col0 = math.floor(source_col_center)
                row_fraction = source_row_center - row0
                col_fraction = source_col_center - col0
                weighted_positions = (
                    (row0, col0, (1 - row_fraction) * (1 - col_fraction)),
                    (row0, col0 + 1, (1 - row_fraction) * col_fraction),
                    (row0 + 1, col0, row_fraction * (1 - col_fraction)),
                    (row0 + 1, col0 + 1, row_fraction * col_fraction),
                )
                weighted_samples = [
                    (sample(row, col), weight)
                    for row, col, weight in weighted_positions
                    if weight > 0
                ]
                valid = bool(weighted_samples) and all(
                    item[0][1] for item in weighted_samples
                )
                if valid:
                    value = sum(item[0][0] * item[1] for item in weighted_samples)
                    valid = math.isfinite(value)
                else:
                    value = float("nan")
            if not valid:
                value = float("nan")
            output.extend(struct.pack("<d", value))
            output_valid.append(valid)

    output_buffer = RasterWindowBuffer(
        window=RasterWindow(0, 0, destination.height, destination.width, source.bands),
        bands=source.bands,
        dtypes=("float64",),
        byte_order="little",
        samples=bytes(output),
    )
    output_metadata = replace(
        destination,
        dtypes=("float64",),
        nodata=(float("nan"),),
        block_shapes=(),
        overview_factors=(),
        driver="FoundryResampled",
    )
    return RasterResampleResult(
        buffer=output_buffer,
        metadata=output_metadata,
        valid=tuple(output_valid),
    )
