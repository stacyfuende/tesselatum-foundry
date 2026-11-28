from __future__ import annotations

import pytest

from tessellatum_foundry.sources import (
    BudgetedRasterRangeReader,
    ExternalDataReference,
    RasterContractError,
    RasterMetadata,
    RasterWindow,
    SourceLimitExceeded,
)


class FakeRangeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def read_range(self, reference, *, offset, length, max_range_bytes):
        self.calls.append((offset, length))
        return b"x" * length


def raster_metadata(**overrides) -> RasterMetadata:
    values = {
        "width": 1024,
        "height": 512,
        "band_count": 3,
        "dtypes": ("uint8", "uint8", "uint16"),
        "transform": (10.0, 2.0, 0.0, 20.0, 0.0, -2.0),
        "crs": "EPSG:3857",
        "nodata": (None, None, 0),
        "block_shapes": ((256, 256), (256, 256), (256, 256)),
        "overview_factors": (2, 4, 8),
    }
    values.update(overrides)
    return RasterMetadata(**values)


def test_raster_window_validates_grid_and_band_selection() -> None:
    metadata = raster_metadata()
    metadata.validate_window(RasterWindow(10, 20, 100, 200, (1, 3)))

    with pytest.raises(RasterContractError, match="beyond"):
        metadata.validate_window(RasterWindow(500, 0, 20, 1))
    with pytest.raises(RasterContractError, match="absent"):
        metadata.validate_window(RasterWindow(0, 0, 1, 1, (4,)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"width": 0},
        {"dtypes": ("uint8",)},
        {"transform": (0, 1, 0, 0, 0, 0)},
        {"nodata": (None,)},
        {"block_shapes": ((256, 256),)},
        {"overview_factors": (4, 2)},
        {"transform": (0, 1, 0, 0, 0, float("nan"))},
        {"dtypes": ("uint8", "uint8", 7)},
        {"nodata": (None, False, 0)},
        {"metadata": {"bad": 1}},
    ],
)
def test_raster_metadata_rejects_invalid_grid_contract(overrides) -> None:
    with pytest.raises((RasterContractError, TypeError)):
        raster_metadata(**overrides)


def test_raster_range_reader_enforces_strong_etag_and_cumulative_budgets() -> None:
    reference = ExternalDataReference(
        provider="example",
        dataset_id="dem",
        uri="https://data.example.test/dem.tif",
        etag='"version-1"',
    )
    adapter = FakeRangeAdapter()
    reader = BudgetedRasterRangeReader(
        adapter, reference, max_requests=2, max_total_bytes=10, max_range_bytes=8
    )

    assert reader.read(offset=0, length=4) == b"xxxx"
    assert reader.read(offset=16, length=6) == b"xxxxxx"
    assert (reader.request_count, reader.bytes_requested) == (2, 10)
    with pytest.raises(SourceLimitExceeded, match="request budget"):
        reader.read(offset=32, length=1)
    with pytest.raises(SourceLimitExceeded, match="per-request"):
        reader.read(offset=0, length=9)


def test_raster_range_reader_requires_strong_validator() -> None:
    adapter = FakeRangeAdapter()
    for etag in (None, 'W/"weak"'):
        reference = ExternalDataReference(
            provider="example",
            dataset_id="dem",
            uri="https://data.example.test/dem.tif",
            etag=etag,
        )
        with pytest.raises(RasterContractError, match="strong source ETag"):
            BudgetedRasterRangeReader(adapter, reference)


def test_failed_range_attempt_still_consumes_budget() -> None:
    class FailingAdapter(FakeRangeAdapter):
        def read_range(self, reference, *, offset, length, max_range_bytes):
            self.calls.append((offset, length))
            raise RuntimeError("provider unavailable")

    reference = ExternalDataReference(
        provider="example",
        dataset_id="dem",
        uri="https://data.example.test/dem.tif",
        etag='"version-1"',
    )
    reader = BudgetedRasterRangeReader(FailingAdapter(), reference, max_requests=1)

    with pytest.raises(RuntimeError):
        reader.read(offset=0, length=1)
    with pytest.raises(SourceLimitExceeded, match="request budget"):
        reader.read(offset=1, length=1)
