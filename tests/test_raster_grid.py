from __future__ import annotations

import math
import struct

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    RasterWindowBuffer,
    plan_destination_grid,
    resample_raster_window,
)


def metadata(width=2, height=2, *, transform=(0, 1, 0, 2, 0, -1), nodata=()):
    return RasterMetadata(
        width=width, height=height, band_count=1, dtypes=("float64",),
        transform=transform, crs="EPSG:3857", nodata=nodata,
    )


def source_buffer(values, *, nodata=()):
    grid = metadata(nodata=nodata)
    return RasterWindowBuffer(
        window=RasterWindow(0, 0, 2, 2, bands=(1,)),
        bands=(1,), dtypes=("float64",), byte_order="little",
        samples=struct.pack("<4d", *values),
    ), grid


def values(result):
    return struct.unpack("<" + "d" * (len(result.buffer.samples) // 8), result.buffer.samples)


def test_plans_outward_snapped_destination_grid_in_same_crs():
    grid = plan_destination_grid(
        metadata(), pixel_width=0.5, pixel_height=0.5, anchor_x=0, anchor_y=0
    )
    assert (grid.width, grid.height) == (4, 4)
    assert grid.transform == (0, 0.5, 0, 2, 0, -0.5)
    assert grid.crs == "EPSG:3857"


def test_nearest_resampling_uses_source_pixel_centres():
    source, source_grid = source_buffer((1, 2, 3, 4))
    destination = plan_destination_grid(
        source_grid, pixel_width=0.5, pixel_height=0.5
    )
    result = resample_raster_window(
        source, source_grid, destination, method="nearest"
    )
    assert values(result) == (
        1, 1, 2, 2,
        1, 1, 2, 2,
        3, 3, 4, 4,
        3, 3, 4, 4,
    )
    assert all(result.valid)
    assert result.metadata.dtypes == ("float64",)
    assert math.isnan(result.metadata.nodata[0]) is False


def test_bilinear_resampling_interpolates_and_propagates_nodata():
    source, source_grid = source_buffer((1, 2, 3, 4))
    destination = metadata(
        width=1, height=1, transform=(0.5, 1, 0, 1.5, 0, -1)
    )
    result = resample_raster_window(
        source, source_grid, destination, method="bilinear"
    )
    assert values(result) == (2.5,)
    assert result.valid == (True,)

    nodata_source, nodata_grid = source_buffer(
        (1, -9999, 3, 4), nodata=(-9999,)
    )
    invalid = resample_raster_window(
        nodata_source, nodata_grid, destination, method="bilinear"
    )
    assert math.isnan(values(invalid)[0])
    assert invalid.valid == (False,)


def test_resampling_rejects_crs_mismatch_and_incomplete_source_window():
    source, source_grid = source_buffer((1, 2, 3, 4))
    wrong_crs = RasterMetadata(
        width=1, height=1, band_count=1, dtypes=("float64",),
        transform=(0.5, 1, 0, 1.5, 0, -1), crs="EPSG:4326",
    )
    with pytest.raises(RasterContractError, match="identical"):
        resample_raster_window(source, source_grid, wrong_crs)

    small = RasterWindowBuffer(
        window=RasterWindow(0, 0, 1, 1, bands=(1,)), bands=(1,),
        dtypes=("float64",), byte_order="little", samples=struct.pack("<d", 1),
    )
    destination = plan_destination_grid(
        source_grid, pixel_width=0.5, pixel_height=0.5
    )
    with pytest.raises(RasterContractError, match="does not cover"):
        resample_raster_window(small, source_grid, destination)
