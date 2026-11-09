from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tessellatum_foundry.validation.raster_statistics import (
    inspect_raster_band_statistics_output,
)
from tessellatum_foundry.capabilities.raster_statistics import (
    RasterStatisticsError,
    raster_band_statistics,
)


def _raster_bytes(values: np.ndarray, *, nodata: float | None = None) -> bytes:
    output = BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=values.shape[2],
        height=values.shape[1],
        count=values.shape[0],
        dtype=values.dtype,
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
        nodata=nodata,
    ) as dataset:
        dataset.write(values)
    return output.getvalue()


def test_raster_statistics_excludes_nodata_and_reports_raw_values():
    source = np.array(
        [[[1, 2], [3, -9999]], [[10, 20], [30, 40]]],
        dtype=np.int16,
    )
    result = raster_band_statistics(_raster_bytes(source, nodata=-9999))

    assert result.statistics["width"] == 2
    assert result.statistics["height"] == 2
    assert result.statistics["selected_band_count"] == 2
    first, second = result.statistics["bands"]
    assert first["valid_pixel_count"] == 3
    assert first["minimum"] == 1
    assert first["maximum"] == 3
    assert first["mean"] == 2
    assert first["standard_deviation"] == pytest.approx(np.std([1, 2, 3]))
    assert second["valid_pixel_count"] == 4
    assert second["mean"] == 25
    assert "32636" in result.crs["wkt"]


def test_raster_statistics_selects_bands_and_rejects_invalid_indexes():
    source = np.array([[[1, 2]], [[10, 20]]], dtype=np.uint8)
    result = raster_band_statistics(_raster_bytes(source), bands=[2])
    assert [band["band"] for band in result.statistics["bands"]] == [2]

    for invalid in ([0], [3], [1, 1], [], ["1"]):
        with pytest.raises(RasterStatisticsError):
            raster_band_statistics(_raster_bytes(source), bands=invalid)


def test_raster_statistics_rejects_empty_or_unreadable_input():
    for invalid in (b"", b"not a raster"):
        with pytest.raises(RasterStatisticsError):
            raster_band_statistics(invalid)


def test_raster_statistics_rejects_band_with_no_valid_pixels():
    source = np.full((1, 2, 2), -9999, dtype=np.int16)
    with pytest.raises(RasterStatisticsError, match="no finite, valid pixels"):
        raster_band_statistics(_raster_bytes(source, nodata=-9999))


def test_raster_statistics_requires_crs():
    output = BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        transform=from_origin(0, 2, 1, 1),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype=np.uint8))
    with pytest.raises(RasterStatisticsError, match="declare a CRS"):
        raster_band_statistics(output.getvalue())


def test_raster_statistics_reports_scale_without_applying_it():
    output = BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=2,
        height=1,
        count=1,
        dtype="uint16",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
    ) as dataset:
        dataset.write(np.array([[[2, 4]]], dtype=np.uint16))
        dataset.scales = (0.5,)
        dataset.offsets = (100.0,)
        dataset.set_band_description(1, "surface temperature DN")

    result = raster_band_statistics(output.getvalue())
    band = result.statistics["bands"][0]
    assert band["mean"] == 3
    assert band["scale"] == 0.5
    assert band["offset"] == 100.0
    assert band["unit"] is None
    assert result.statistics["value_semantics"] == "raw_stored_samples"


def test_raster_statistics_aggregates_multiple_tiled_windows_exactly():
    values = np.arange(600 * 700, dtype=np.int32).reshape(1, 600, 700)
    output = BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        width=700,
        height=600,
        count=1,
        dtype="int32",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
        tiled=True,
        blockxsize=256,
        blockysize=256,
        nodata=-1,
    ) as dataset:
        dataset.write(values)
        # Include a nodata pixel in a later tile to exercise cross-window counts.
        dataset.write(np.array([[-1]], dtype=np.int32), 1, window=((300, 301), (300, 301)))

    result = raster_band_statistics(output.getvalue())
    band = result.statistics["bands"][0]
    expected = values.astype(np.float64)
    expected[0, 300, 300] = np.nan
    valid = expected[np.isfinite(expected)]

    assert band["valid_pixel_count"] == valid.size
    assert band["minimum"] == float(np.min(valid))
    assert band["maximum"] == float(np.max(valid))
    assert band["mean"] == pytest.approx(float(np.mean(valid)), rel=1e-12)
    assert band["standard_deviation"] == pytest.approx(
        float(np.std(valid, ddof=0)), rel=1e-12
    )


def test_raster_statistics_excludes_non_finite_float_samples():
    source = np.array(
        [[[1.0, np.nan, np.inf], [-np.inf, 5.0, -9999.0]]],
        dtype=np.float32,
    )
    result = raster_band_statistics(_raster_bytes(source, nodata=-9999.0))
    band = result.statistics["bands"][0]

    assert band["valid_pixel_count"] == 2
    assert band["minimum"] == 1.0
    assert band["maximum"] == 5.0
    assert band["mean"] == 3.0
    assert band["standard_deviation"] == 2.0



def test_raster_statistics_windowed_output_passes_independent_critic():
    source = np.arange(600 * 700, dtype=np.int32).reshape(1, 600, 700)
    raster = BytesIO()
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=700,
        height=600,
        count=1,
        dtype="int32",
        crs="EPSG:32636",
        transform=from_origin(500000, 1000000, 10, 10),
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dataset:
        dataset.write(source)

    raster_bytes = raster.getvalue()
    result = raster_band_statistics(raster_bytes)
    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=raster_bytes,
        output={"statistics": result.statistics, "crs": result.crs},
    )

    assert inspection.passed, inspection.findings



def test_raster_statistics_critic_rejects_tampered_summary():
    source = np.array([[[1, 2], [3, 4]]], dtype=np.uint8)
    raster_bytes = _raster_bytes(source)
    result = raster_band_statistics(raster_bytes)
    tampered = {
        "statistics": {
            **result.statistics,
            "bands": [
                {
                    **result.statistics["bands"][0],
                    "valid_pixel_count": 3,
                    "mean": 999,
                }
            ],
        },
        "crs": result.crs,
    }

    inspection = inspect_raster_band_statistics_output(
        input_raster_bytes=raster_bytes,
        output=tampered,
    )

    assert not inspection.passed
    failed_codes = {finding.code for finding in inspection.findings if finding.status == "failed"}
    assert "raster_output.valid_pixel_counts" in failed_codes
    assert "raster_output.numeric_statistics" in failed_codes
