from __future__ import annotations

import hashlib

import pytest

from tessellatum_foundry.sources import (
    BudgetedRasterRangeReader,
    ExternalDataReference,
    RasterTileSelection,
    SourceLimitExceeded,
    read_selected_tiff_tiles,
)


class MemoryRanges:
    def __init__(self):
        self.calls = []

    def read_range(self, reference, *, offset, length, max_range_bytes):
        self.calls.append((offset, length))
        return bytes([offset % 251]) * length


def selection(offset, length):
    return RasterTileSelection(
        band=0, tile_row=0, tile_column=0, block_index=0,
        byte_offset=offset, byte_length=length,
        tile_row_offset=0, tile_column_offset=0, tile_height=16, tile_width=16,
        window_row_offset=0, window_column_offset=0, window_height=8, window_width=8,
    )


def reader(adapter, **limits):
    reference = ExternalDataReference(
        provider="test", dataset_id="raster",
        uri="https://example.test/raster.tif", etag='"v1"',
    )
    return BudgetedRasterRangeReader(adapter, reference, **limits)


def test_reads_tiles_sequentially_and_attaches_checksum():
    adapter = MemoryRanges()
    bounded = reader(adapter, max_requests=2, max_total_bytes=12, max_range_bytes=8)
    tiles = read_selected_tiff_tiles(bounded, [selection(4, 5), selection(20, 7)])

    first = next(tiles)
    assert adapter.calls == [(4, 5)]
    assert first.payload == bytes([4]) * 5
    assert first.sha256 == hashlib.sha256(first.payload).hexdigest()
    second = next(tiles)
    assert adapter.calls == [(4, 5), (20, 7)]
    assert second.payload == bytes([20]) * 7
    with pytest.raises(StopIteration):
        next(tiles)


def test_tile_reads_share_cumulative_budget():
    adapter = MemoryRanges()
    bounded = reader(adapter, max_requests=1, max_total_bytes=8, max_range_bytes=8)
    tiles = read_selected_tiff_tiles(bounded, [selection(0, 8), selection(8, 1)])
    next(tiles)
    with pytest.raises(SourceLimitExceeded, match="request budget"):
        next(tiles)


def test_tile_payload_is_not_yielded_when_range_adapter_returns_short_data():
    class ShortRanges(MemoryRanges):
        def read_range(self, reference, *, offset, length, max_range_bytes):
            self.calls.append((offset, length))
            return b"x"

    tiles = read_selected_tiff_tiles(
        reader(ShortRanges()), [selection(0, 4)]
    )
    with pytest.raises(ValueError, match="exact requested bytes"):
        next(tiles)
