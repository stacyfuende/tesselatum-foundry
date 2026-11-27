from __future__ import annotations

import math
import struct

import pytest

from tessellatum_foundry.sources import (
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    RasterWindowBuffer,
    apply_nodata_aware_binary,
)


def metadata(*, nodata=()):
    return RasterMetadata(
        width=4, height=1, band_count=1, dtypes=("float64",),
        transform=(0, 1, 0, 0, 0, -1), crs="EPSG:3857", nodata=nodata,
    )


def buffer(values, *, bands=(1,), byte_order="little"):
    prefix = "<" if byte_order == "little" else ">"
    return RasterWindowBuffer(
        window=RasterWindow(0, 0, 1, len(values)),
        bands=bands,
        dtypes=("float64",),
        byte_order=byte_order,
        samples=b"".join(struct.pack(prefix + "d", value) for value in values),
    )


def unpack(result):
    return struct.unpack("<" + "d" * 4, result.buffer.samples)


def test_add_propagates_nodata_and_emits_explicit_validity():
    left = buffer((1, -9999, 3, 4))
    right = buffer((10, 20, 30, 40), byte_order="big")
    result = apply_nodata_aware_binary(
        left, right, metadata(nodata=(-9999,)), metadata(), operation="add"
    )
    values = unpack(result)
    assert values[0] == 11
    assert math.isnan(values[1])
    assert values[2:] == (33, 44)
    assert result.valid == (True, False, True, True)
    assert result.buffer.dtypes == ("float64",)
    assert result.buffer.byte_order == "little"


def test_division_by_zero_is_invalid_not_infinite():
    result = apply_nodata_aware_binary(
        buffer((8, 9, 10, 12)), buffer((2, 0, 5, 3)),
        metadata(), metadata(), operation="divide",
    )
    values = unpack(result)
    assert values[0] == 4
    assert math.isnan(values[1])
    assert values[2:] == (2, 4)
    assert result.valid == (True, False, True, True)


def test_arithmetic_rejects_misaligned_windows_and_unsupported_operations():
    left = buffer((1, 2, 3, 4))
    right = RasterWindowBuffer(
        window=RasterWindow(0, 1, 1, 3), bands=(1,), dtypes=("float64",),
        byte_order="little", samples=struct.pack("<3d", 1, 2, 3),
    )
    with pytest.raises(RasterContractError, match="identical windows"):
        apply_nodata_aware_binary(
            left, right, metadata(), metadata(), operation="add"
        )
    with pytest.raises(RasterContractError, match="Unsupported"):
        apply_nodata_aware_binary(
            left, left, metadata(), metadata(), operation="power"
        )
