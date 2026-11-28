from __future__ import annotations

import struct

import pytest

from tessellatum_foundry.sources.raster import RasterWindow
from tessellatum_foundry.sources.window_assembly import RasterWindowBuffer
from tessellatum_foundry.storage.raster_comparison import (
    RasterComparisonError,
    compare_raster_window_artifacts,
)
from tessellatum_foundry.storage.raster_window import (
    decode_raster_window_artifact,
    encode_raster_window_artifact,
)


def artifact(
    samples,
    *,
    validity=(True, True, True),
    transform=(0, 1, 0, 3, 0, -1),
    crs="EPSG:4326",
):
    buf = RasterWindowBuffer(
        window=RasterWindow(0, 0, 1, 3, (1,)),
        bands=(1,),
        dtypes=("float32",),
        byte_order="little",
        samples=struct.pack("<3f", *samples),
    )
    return decode_raster_window_artifact(encode_raster_window_artifact(
        buf, validity=validity,
        grid={"width": 3, "height": 1, "transform": list(transform), "crs": crs},
        provenance={"test": True},
    ))


def test_numeric_metrics_and_validity_overlap():
    result = compare_raster_window_artifacts(
        artifact([1, 2, 3], validity=(True, False, True)),
        artifact([2, 4, 6], validity=(True, True, True)),
    )
    band = result["bands"][0]
    assert result["valid_both"] == 2
    assert result["valid_only_b"] == 1
    assert band["bias_b_minus_a"] == pytest.approx(2)
    assert band["mean_absolute_error"] == pytest.approx(2)
    assert band["root_mean_square_error"] == pytest.approx(2.2360679775)
    assert band["maximum_absolute_difference"] == pytest.approx(3)
    assert band["correlation"] == pytest.approx(1)


def test_comparison_rejects_different_grid_or_window():
    with pytest.raises(RasterComparisonError, match="CRS and transform"):
        compare_raster_window_artifacts(
            artifact([1, 2, 3]), artifact([1, 2, 3], crs="EPSG:3857")
        )
    with pytest.raises(RasterComparisonError, match="transform"):
        compare_raster_window_artifacts(
            artifact([1, 2, 3]),
            artifact([1, 2, 3], transform=(0, 2, 0, 3, 0, -2)),
        )


def test_comparison_rejects_no_shared_valid_pixels():
    with pytest.raises(RasterComparisonError, match="No pixels"):
        compare_raster_window_artifacts(
            artifact([1, 2, 3], validity=(True, False, False)),
            artifact([1, 2, 3], validity=(False, True, True)),
        )
