from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tessellatum_foundry.capabilities.raster_statistics import (
    RasterStatisticsError,
    raster_band_statistics,
)
from tessellatum_foundry.validation.raster_statistics import (
    inspect_raster_band_statistics_output,
)


def _source() -> bytes:
    stream = BytesIO()
    with rasterio.open(
        stream,
        "w",
        driver="GTiff",
        width=3,
        height=2,
        count=1,
        dtype="int16",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
        nodata=-9999,
    ) as dataset:
        dataset.write(np.array([[[1, 2, 3], [4, -9999, 6]]], dtype=np.int16))
    return stream.getvalue()


def test_raster_statistics_output_critic_accepts_exact_kernel_result():
    source = _source()
    result = raster_band_statistics(source)
    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=source,
        output={"statistics": result.statistics, "crs": result.crs},
    )
    assert inspection.passed
    assert {finding.code for finding in inspection.findings} >= {
        "raster_output.crs_matches_source",
        "raster_output.dimensions",
        "raster_output.numeric_statistics",
        "raster_output.valid_pixel_counts",
    }


def test_raster_statistics_output_critic_rejects_tampered_values_and_dimensions():
    source = _source()
    result = raster_band_statistics(source)
    tampered = {
        "statistics": {
            **result.statistics,
            "width": 999,
            "bands": [
                {
                    **result.statistics["bands"][0],
                    "minimum": 10**1000,
                    "mean": 12345,
                    "valid_pixel_count": 99,
                }
            ],
        },
        "crs": result.crs,
    }
    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=source,
        output=tampered,
    )
    failed_codes = {
        finding.code for finding in inspection.findings if finding.status == "failed"
    }
    assert {
        "raster_output.dimensions",
        "raster_output.valid_pixel_counts",
        "raster_output.numeric_statistics",
    } <= failed_codes


def test_raster_statistics_preserves_large_int64_extrema_and_variance():
    base = 2**60
    source_stream = BytesIO()
    with rasterio.open(
        source_stream,
        "w",
        driver="GTiff",
        width=4,
        height=1,
        count=1,
        dtype="int64",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
    ) as dataset:
        dataset.write(
            np.array([[[base, base + 1, base + 2, base + 3]]], dtype=np.int64)
        )
    source = source_stream.getvalue()

    result = raster_band_statistics(source)
    band = result.statistics["bands"][0]
    assert band["minimum"] == base
    assert band["maximum"] == base + 3
    assert band["standard_deviation"] == pytest.approx(np.std([0, 1, 2, 3], ddof=0))

    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=source,
        output={"statistics": result.statistics, "crs": result.crs},
    )
    assert inspection.passed


def test_raster_statistics_excludes_internal_mask_and_non_finite_float_samples():
    stream = BytesIO()
    with rasterio.open(
        stream,
        "w",
        driver="GTiff",
        width=5,
        height=1,
        count=1,
        dtype="float32",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
    ) as dataset:
        dataset.write(
            np.array([[[1.5, 100.0, np.nan, np.inf, 2.5]]], dtype=np.float32)
        )
        dataset.write_mask(np.array([[255, 0, 255, 255, 255]], dtype=np.uint8))

    result = raster_band_statistics(stream.getvalue())
    band = result.statistics["bands"][0]
    assert band["valid_pixel_count"] == 2
    assert band["minimum"] == 1.5
    assert band["maximum"] == 2.5
    assert band["mean"] == 2.0
    assert band["standard_deviation"] == 0.5
    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=stream.getvalue(),
        output={"statistics": result.statistics, "crs": result.crs},
    )
    assert inspection.passed


def test_raster_statistics_rejects_band_with_no_finite_valid_pixels():
    stream = BytesIO()
    with rasterio.open(
        stream,
        "w",
        driver="GTiff",
        width=3,
        height=1,
        count=1,
        dtype="float32",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
    ) as dataset:
        dataset.write(np.array([[[np.nan, np.inf, -np.inf]]], dtype=np.float32))

    with pytest.raises(RasterStatisticsError, match="no finite, valid pixels"):
        raster_band_statistics(stream.getvalue())

def test_raster_statistics_preserves_large_uint64_extrema_and_variance():
    maximum = np.iinfo(np.uint64).max
    source_stream = BytesIO()
    with rasterio.open(
        source_stream,
        "w",
        driver="GTiff",
        width=4,
        height=1,
        count=1,
        dtype="uint64",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
    ) as dataset:
        dataset.write(
            np.array(
                [[[maximum - 3, maximum - 2, maximum - 1, maximum]]],
                dtype=np.uint64,
            )
        )
    source = source_stream.getvalue()

    result = raster_band_statistics(source)
    band = result.statistics["bands"][0]
    assert band["minimum"] == int(maximum - 3)
    assert band["maximum"] == int(maximum)
    assert band["standard_deviation"] == pytest.approx(
        np.std([0, 1, 2, 3], ddof=0)
    )

    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=source,
        output={"statistics": result.statistics, "crs": result.crs},
    )
    assert inspection.passed
