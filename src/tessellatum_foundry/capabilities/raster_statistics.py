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


def _windowed_statistics(
    dataset: rasterio.io.DatasetReader, band_index: int
) -> dict[str, float | int]:
    """Exhaustively compute count/min/max/mean/population SD with bounded memory."""
    count = 0
    mean = 0.0
    m2 = 0.0
    minimum: float | int = math.inf
    maximum: float | int = -math.inf
    integer_baseline: int | None = None

    for _, window in dataset.block_windows(band_index):
        masked = dataset.read(band_index, window=window, masked=True)
        raw_values = masked.compressed()
        if raw_values.size == 0:
            continue
        if np.issubdtype(raw_values.dtype, np.integer):
            if integer_baseline is None:
                integer_baseline = int(raw_values[0])
            # Subtract as Python integers before float conversion. This avoids
            # losing low-order bits for int64/uint64 samples above 2**53.
            values = np.fromiter(
                (int(value) - integer_baseline for value in raw_values),
                dtype=np.float64,
                count=int(raw_values.size),
            )
            chunk_min = int(np.min(raw_values))
            chunk_max = int(np.max(raw_values))
        else:
            values = np.asarray(raw_values, dtype=np.float64)
            values = values[np.isfinite(values)]
            if values.size == 0:
                continue
            chunk_min = float(np.min(values))
            chunk_max = float(np.max(values))

        chunk_count = int(values.size)
        chunk_mean = float(np.mean(values, dtype=np.float64))
        centered = values - chunk_mean
        chunk_m2 = float(np.dot(centered, centered))

        if count == 0:
            count, mean, m2 = chunk_count, chunk_mean, chunk_m2
        else:
            combined = count + chunk_count
            delta = chunk_mean - mean
            m2 += chunk_m2 + delta * delta * count * chunk_count / combined
            mean += delta * chunk_count / combined
            count = combined
        minimum = min(minimum, chunk_min)
        maximum = max(maximum, chunk_max)

    if count == 0:
        raise RasterStatisticsError(
            f"Band {band_index} contains no finite, valid pixels."
        )
    variance = m2 / count
    standard_deviation = math.sqrt(max(0.0, variance))
    reported_mean = float(integer_baseline + mean) if integer_baseline is not None else mean
    finite_outputs = (minimum, maximum, reported_mean, standard_deviation)
    if not all(math.isfinite(float(value)) for value in finite_outputs):
        raise RasterStatisticsError(
            f"Band {band_index} statistics exceed finite float64 output range."
        )
    return {
        "valid_pixel_count": count,
        "minimum": minimum,
        "maximum": maximum,
        "mean": reported_mean,
        "standard_deviation": standard_deviation,
    }


def raster_band_statistics(
    raster_bytes: bytes,
    *,
    bands: Sequence[int] | None = None,
) -> RasterStatisticsOutput:
    """Calculate exact statistics over valid stored samples in selected bands.

    Raster blocks are processed incrementally, so working memory is bounded by
    the largest source block rather than the full raster dimensions. Nodata and
    masked pixels are excluded. Values are raw stored samples: GDAL scale/offset
    metadata is reported but deliberately not applied. Standard deviation is
    population standard deviation (ddof=0), accumulated in float64.
    """
    if not isinstance(raster_bytes, bytes) or not raster_bytes:
        raise RasterStatisticsError("Input must be non-empty raster bytes.")
    try:
        with rasterio.MemoryFile(raster_bytes) as memory_file:
            with memory_file.open() as dataset:
                if dataset.width < 1 or dataset.height < 1 or dataset.count < 1:
                    raise RasterStatisticsError(
                        "Raster dimensions and band count must be positive."
                    )
                selected = _normalize_bands(bands, dataset.count)
                crs = dataset.crs
                if crs is None:
                    raise RasterStatisticsError("Raster must declare a CRS.")
                band_results: list[dict[str, Any]] = []
                for band_index in selected:
                    summary = _windowed_statistics(dataset, band_index)
                    band_results.append(
                        {
                            "band": band_index,
                            "dtype": dataset.dtypes[band_index - 1],
                            **summary,
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
