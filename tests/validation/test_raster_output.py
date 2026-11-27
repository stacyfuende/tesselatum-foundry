from __future__ import annotations

import struct

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.sources import RasterMetadata, RasterWindow
from tessellatum_foundry.sources.window_assembly import RasterWindowBuffer
from tessellatum_foundry.validation.raster_output import inspect_raster_window_output


def test_raster_window_capability_is_registered_and_exact():
    registry = CapabilityRegistry()
    capability = registry.get("raster.window", "1.0.0")
    assert capability["category"] == "raster"
    assert registry.require_exact(capability) == capability


def test_raster_window_critic_accepts_exact_bounded_output():
    metadata = RasterMetadata(
        width=4, height=3, band_count=1, dtypes=("uint16",),
        transform=(10, 2, 0, 20, 0, -2), crs="EPSG:3857",
    )
    window = RasterWindow(1, 1, 2, 2, bands=(1,))
    buffer = RasterWindowBuffer(
        window=window, bands=(1,), dtypes=("uint16",),
        byte_order="little", samples=struct.pack("<4H", 1, 2, 3, 4),
    )
    result = inspect_raster_window_output(
        buffer=buffer, metadata=metadata, requested_window=window,
        requested_bands=(1,), validity=(True, True, False, True),
    )
    assert result.passed
    assert result.sample_count == 4
    assert result.byte_count == 8


def test_raster_window_critic_rejects_wrong_window_band_and_byte_length():
    metadata = RasterMetadata(
        width=4, height=3, band_count=2, dtypes=("uint16", "uint8"),
        transform=(10, 2, 0, 20, 0, -2), crs="EPSG:3857",
    )
    requested = RasterWindow(0, 0, 2, 2, bands=(2, 1))
    wrong = RasterWindow(0, 0, 1, 2, bands=(1,))
    buffer = RasterWindowBuffer(
        window=wrong, bands=(1,), dtypes=("uint16",),
        byte_order="little", samples=struct.pack("<2H", 1, 2),
    )
    result = inspect_raster_window_output(
        buffer=buffer, metadata=metadata, requested_window=requested,
        requested_bands=(2, 1), validity=(True,),
    )
    assert not result.passed
    assert {finding.code for finding in result.findings if finding.status == "failed"} == {
        "raster.window_matches_request",
        "raster.band_order_matches_request",
        "raster.source_grid_and_dtypes",
        "raster.output_byte_length",
        "raster.validity_mask",
    }


def test_raster_window_critic_enforces_output_budget():
    metadata = RasterMetadata(
        width=2, height=2, band_count=1, dtypes=("float64",),
        transform=(0, 1, 0, 2, 0, -1), crs="EPSG:3857",
    )
    window = RasterWindow(0, 0, 2, 2, bands=(1,))
    buffer = RasterWindowBuffer(
        window=window, bands=(1,), dtypes=("float64",),
        byte_order="little", samples=struct.pack("<4d", 1, 2, 3, 4),
    )
    result = inspect_raster_window_output(
        buffer=buffer, metadata=metadata, requested_window=window,
        requested_bands=(1,), max_output_bytes=8,
    )
    assert not result.passed
