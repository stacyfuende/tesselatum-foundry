from __future__ import annotations

import math
import struct

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    RasterWindowBuffer,
    build_validity_mask,
    sample_is_valid,
    window_validity_mask,
)


def test_scalar_nodata_validity_handles_regular_and_nan_values():
    assert sample_is_valid(7, None)
    assert not sample_is_valid(-9999, -9999)
    assert sample_is_valid(5, -9999)
    assert not sample_is_valid(float("nan"), float("nan"))
    assert sample_is_valid(3.5, float("nan"))


def test_build_mask_requires_all_bands_valid_and_checks_shapes():
    mask = build_validity_mask(
        ((1, 2), (1, -9999), (-9999, -9999)),
        (None, -9999),
        band_count=2,
    )
    assert mask == (True, False, False)
    with pytest.raises(RasterContractError, match="align"):
        build_validity_mask(((1,),), (None, None), band_count=1)
    with pytest.raises(RasterContractError, match="sample count"):
        build_validity_mask(((1,),), (None, None), band_count=2)


def test_window_mask_respects_selected_band_order_and_nodata():
    window = RasterWindow(0, 0, 2, 2, bands=(2, 1))
    buffer = RasterWindowBuffer(
        window=window,
        bands=(2, 1),
        dtypes=("uint8", "uint8"),
        byte_order="little",
        samples=bytes((0, 5, 255, 5, 255, 7, 3, 7)),
    )
    metadata = RasterMetadata(
        width=2, height=2, band_count=2, dtypes=("uint8", "uint8"),
        transform=(0, 1, 0, 0, 0, -1), nodata=(None, 255),
    )
    assert window_validity_mask(buffer, metadata) == (True, False, False, True)


def test_window_mask_without_nodata_marks_all_pixels_valid():
    window = RasterWindow(0, 0, 1, 2)
    buffer = RasterWindowBuffer(
        window=window, bands=(1,), dtypes=("uint8",), byte_order="little",
        samples=bytes((0, 255)),
    )
    metadata = RasterMetadata(
        width=2, height=1, band_count=1, dtypes=("uint8",),
        transform=(0, 1, 0, 0, 0, -1),
    )
    assert window_validity_mask(buffer, metadata) == (True, True)
