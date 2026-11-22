from __future__ import annotations

from io import BytesIO

import numpy as np
import rasterio
from rasterio.transform import from_origin

from tessellatum_foundry.capabilities.raster_statistics import raster_band_statistics
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
