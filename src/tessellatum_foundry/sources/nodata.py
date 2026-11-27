"""Raster sample validity helpers for explicit NoData-aware processing."""
from __future__ import annotations

import math
import struct
from collections.abc import Iterable, Sequence

from .raster import RasterContractError, RasterMetadata
from .window_assembly import RasterWindowBuffer


def sample_is_valid(value: int | float, nodata: int | float | None) -> bool:
    """Return whether a scalar sample is valid under its explicit NoData value."""
    if nodata is None:
        return True
    if isinstance(nodata, float) and math.isnan(nodata):
        return not (isinstance(value, float) and math.isnan(value))
    return value != nodata


def build_validity_mask(
    samples: Iterable[Sequence[int | float]],
    nodata: Sequence[int | float | None],
    *,
    band_count: int,
) -> tuple[bool, ...]:
    """Build a pixel mask; a pixel is valid only when all its bands are valid."""
    if band_count < 1 or len(nodata) != band_count:
        raise RasterContractError("NoData values must align with the selected band count.")
    mask = []
    for pixel in samples:
        if len(pixel) != band_count:
            raise RasterContractError("Pixel sample count does not match the selected bands.")
        mask.append(all(sample_is_valid(value, nodata[index]) for index, value in enumerate(pixel)))
    return tuple(mask)


def window_validity_mask(
    buffer: RasterWindowBuffer,
    metadata: RasterMetadata,
) -> tuple[bool, ...]:
    """Return a pixel-validity mask for an assembled window in selected-band order."""
    buffer.window.validate_against(metadata)
    if buffer.byte_order not in ("little", "big"):
        raise RasterContractError("Raster window byte order must be 'little' or 'big'.")
    expected_bands = buffer.window.bands or tuple(range(1, metadata.band_count + 1))
    if (
        not buffer.bands
        or buffer.bands != expected_bands
        or len(buffer.bands) != len(buffer.dtypes)
        or len(set(buffer.bands)) != len(buffer.bands)
    ):
        raise RasterContractError("Raster window buffer band selection is inconsistent.")
    if buffer.dtypes != tuple(metadata.dtypes[band - 1] for band in buffer.bands):
        raise RasterContractError(\n            "Raster window buffer dtypes do not match selected metadata bands."\n        )
    selected_nodata = tuple(metadata.nodata[band - 1] for band in buffer.bands)
    if not metadata.nodata:
        selected_nodata = (None,) * len(buffer.bands)
    samples = buffer.samples
    widths = {"uint8": 1, "int8": 1, "uint16": 2, "int16": 2,
              "uint32": 4, "int32": 4, "uint64": 8, "int64": 8,
              "float32": 4, "float64": 8}
    try:
        sample_widths = tuple(widths[dtype] for dtype in buffer.dtypes)
    except KeyError as error:
        raise RasterContractError("Unsupported dtype for NoData mask.") from error
    pixel_width = sum(sample_widths)
    expected_bytes = buffer.window.width * buffer.window.height * pixel_width
    if len(samples) != expected_bytes:
        raise RasterContractError("Raster window buffer has an unexpected byte length.")
    byte_order = "<" if buffer.byte_order == "little" else ">"
    fmt_by_dtype = {"uint8": "B", "int8": "b", "uint16": "H", "int16": "h",
                    "uint32": "I", "int32": "i", "uint64": "Q", "int64": "q",
                    "float32": "f", "float64": "d"}
    mask = []
    for pixel_index in range(buffer.window.width * buffer.window.height):
        offset = pixel_index * pixel_width
        valid = True
        band_offset = 0
        for band_index, dtype in enumerate(buffer.dtypes):
            value = struct.unpack_from(byte_order + fmt_by_dtype[dtype], samples,
                                      offset + band_offset)[0]
            valid = valid and sample_is_valid(value, selected_nodata[band_index])
            band_offset += sample_widths[band_index]
        mask.append(valid)
    return tuple(mask)
