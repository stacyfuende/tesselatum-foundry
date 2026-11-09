"""Raster band statistics capability implemented with Rasterio/GDAL."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import numpy as np
import rasterio
from rasterio.errors import RasterioError


class RasterStatisticsError(ValueError):
    """Raised when a raster statistics request violates the capability contract."""


@dataclass(frozen=True)
class RasterStatisticsOutput:
    """Deterministic per-band summary of stored raster sample values."""

    statistics: dict[str, Any]
    crs: dict[str, Any]


def _normalize_bands(bands: Sequence[int] | None, count: int) -> tuple[int, ...]:
    if bands is None:
        return tuple(range(1, count + 1))
    if isinstance(bands, (str, bytes)) or not isinstance(bands, Sequence) or not bands:
        raise RasterStatisticsError("bands must be a non-empty sequence of 1-based band indexes.")
    normalized: list[int] = []
    for band in bands:
        if type(band) is not int or not 1 <= band <= count:
            raise RasterStatisticsError(
                f"Band indexes must be integers between 1 and {count}."
            )
        if band in normalized:
            raise RasterStatisticsError("Band indexes must not contain duplicates.")
        normalized.append(band)
    return tuple(normalized)


def raster_band_statistics(
    raster_bytes: bytes,
    *,
    bands: Sequence[int] | None = None,
) -> RasterStatisticsOutput:
    """Calculate exact statistics over valid stored samples in selected bands.

    Nodata and masked pixels are excluded. Values are raw stored samples: GDAL
    scale/offset metadata is reported but deliberately not applied. Statistics
    are population statistics (ddof=0), computed in float64.
    """
    if not isinstance(raster_bytes, bytes) or not raster_bytes:
        raise RasterStatisticsError("Input must be non-empty raster bytes.")
    try:
        with rasterio.MemoryFile(raster_bytes) as memory_file:
            with memory_file.open() as dataset:
                if dataset.width < 1 or dataset.height < 1 or dataset.count < 1:
                    raise RasterStatisticsError("Raster dimensions and band count must be positive.")
                selected = _normalize_bands(bands, dataset.count)
                crs = dataset.crs
                if crs is None:
                    raise RasterStatisticsError("Raster must declare a CRS.")
                band_results: list[dict[str, Any]] = []
                for band_index in selected:
                    samples = dataset.read(band_index, masked=True)
                    values = np.asarray(samples.compressed(), dtype=np.float64)
                    values = values[np.isfinite(values)]
                    if values.size == 0:
                        raise RasterStatisticsError(
                            f"Band {band_index} contains no finite, valid pixels."
                        )
                    band_results.append(
                        {
                            "band": band_index,
                            "dtype": dataset.dtypes[band_index - 1],
                            "valid_pixel_count": int(values.size),
                            "minimum": float(np.min(values)),
                            "maximum": float(np.max(values)),
                            "mean": float(np.mean(values, dtype=np.float64)),
                            "standard_deviation": float(np.std(values, dtype=np.float64)),
                            "scale": float(dataset.scales[band_index - 1]),
                            "offset": float(dataset.offsets[band_index - 1]),
                            "unit": dataset.units[band_index - 1],
                        }
                    )
                return RasterStatisticsOutput(
                    statistics={
                        "width": int(dataset.width),
                        "height": int(dataset.height),
                        "selected_band_count": len(selected),
                        "bands": band_results,
                        "value_semantics": "raw_stored_samples",
                        "standard_deviation": "population",
                    },
                    crs={"wkt": crs.to_wkt()},
                )
    except RasterStatisticsError:
        raise
    except (RasterioError, OSError, ValueError, TypeError) as error:
        raise RasterStatisticsError(f"Input is not a readable supported raster: {error}") from error
