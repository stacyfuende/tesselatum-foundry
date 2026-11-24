"""Provider-neutral raster grid and bounded range-read contracts.

These value objects describe raster semantics; they do not decode TIFF/COG
metadata or pixel blocks. A format reader must establish these values from
validated source bytes before constructing RasterMetadata.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from .models import ExternalDataReference, SourceLimitExceeded


class RasterContractError(ValueError):
    """A raster grid, window, or range request violates its contract."""


class _RangeSource(Protocol):
    def read_range(
        self,
        reference: ExternalDataReference,
        *,
        offset: int,
        length: int,
        max_range_bytes: int = 16 * 1024 * 1024,
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class RasterWindow:
    """A zero-based pixel window with optional one-based band selection."""

    row_offset: int
    column_offset: int
    height: int
    width: int
    bands: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        values = (self.row_offset, self.column_offset, self.height, self.width)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("Raster window offsets and dimensions must be integers.")
        if self.row_offset < 0 or self.column_offset < 0:
            raise RasterContractError("Raster window offsets must be non-negative.")
        if self.height < 1 or self.width < 1:
            raise RasterContractError("Raster window dimensions must be positive.")
        if any(isinstance(band, bool) or not isinstance(band, int) for band in self.bands):
            raise TypeError("Raster band indexes must be integers.")
        if any(band < 1 for band in self.bands) or len(set(self.bands)) != len(self.bands):
            raise RasterContractError("Raster bands must be unique, one-based positive indexes.")

    def validate_against(self, metadata: RasterMetadata) -> None:
        """Reject windows outside the declared grid or band range."""
        if (
            self.column_offset + self.width > metadata.width
            or self.row_offset + self.height > metadata.height
        ):
            raise RasterContractError("Raster window extends beyond the source grid.")
        if any(band > metadata.band_count for band in self.bands):
            raise RasterContractError("Raster window selects a band absent from the source.")


@dataclass(frozen=True, slots=True)
class RasterMetadata:
    """Validated raster grid metadata independent of a specific pixel library.

    transform uses the six affine coefficients in GDAL order:
    (x_origin, pixel_width, row_rotation, y_origin, column_rotation, pixel_height).
    crs is a normalized CRS identifier or WKT string; it may be absent for
    ungeoreferenced rasters, which spatial operations must reject as needed.
    """

    width: int
    height: int
    band_count: int
    dtypes: tuple[str, ...]
    transform: tuple[float, float, float, float, float, float]
    crs: str | None = None
    nodata: tuple[int | float | None, ...] = ()
    block_shapes: tuple[tuple[int, int], ...] = ()
    overview_factors: tuple[int, ...] = ()
    driver: str = "GTiff"
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        dimensions = (self.width, self.height, self.band_count)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in dimensions):
            raise TypeError("Raster dimensions and band count must be integers.")
        if any(value < 1 for value in dimensions):
            raise RasterContractError("Raster dimensions and band count must be positive.")
        if len(self.dtypes) != self.band_count or any(not value for value in self.dtypes):
            raise RasterContractError("A non-empty dtype is required for every raster band.")
        if len(self.transform) != 6 or any(not math.isfinite(value) for value in self.transform):
            raise RasterContractError("Raster affine transform must contain six finite values.")
        if self.transform[1] * self.transform[5] - self.transform[2] * self.transform[4] == 0:
            raise RasterContractError("Raster affine transform must be invertible.")
        if self.nodata and len(self.nodata) != self.band_count:
            raise RasterContractError("NoData values must align with the raster band count.")
        if self.block_shapes and len(self.block_shapes) != self.band_count:
            raise RasterContractError("Block shapes must align with the raster band count.")
        if any(
            len(shape) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 1
                   for value in shape)
            for shape in self.block_shapes
        ):
            raise RasterContractError("Each raster block shape must contain positive dimensions.")
        if (
            any(isinstance(value, bool) or not isinstance(value, int) or value <= 1
                for value in self.overview_factors)
            or tuple(sorted(set(self.overview_factors))) != self.overview_factors
        ):
            raise RasterContractError("Overview factors must be unique, sorted integers above one.")
        if self.crs is not None and not self.crs.strip():
            raise RasterContractError("CRS must be non-empty when supplied.")
        if not self.driver.strip():
            raise RasterContractError("Raster driver must be non-empty.")

    def validate_window(self, window: RasterWindow) -> None:
        window.validate_against(self)


class BudgetedRasterRangeReader:
    """Apply cumulative request/byte limits to one ETag-pinned raster source.

    The current HTTP range adapter enforces If-Match when reference.etag is
    present. This wrapper requires that validator and counts attempted
    requests, including failed requests, so retries cannot evade the budget.
    """

    def __init__(
        self,
        adapter: _RangeSource,
        reference: ExternalDataReference,
        *,
        max_requests: int = 256,
        max_total_bytes: int = 64 * 1024 * 1024,
        max_range_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        for name, value in (
            ("max_requests", max_requests),
            ("max_total_bytes", max_total_bytes),
            ("max_range_bytes", max_range_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if reference.etag is None or not reference.etag.strip() or reference.etag.startswith("W/"):
            raise RasterContractError("Raster range reads require a strong source ETag.")
        if max_range_bytes > max_total_bytes:
            raise ValueError("max_range_bytes cannot exceed max_total_bytes.")
        self.adapter = adapter
        self.reference = reference
        self.max_requests = max_requests
        self.max_total_bytes = max_total_bytes
        self.max_range_bytes = max_range_bytes
        self.request_count = 0
        self.bytes_requested = 0

    def read(self, *, offset: int, length: int) -> bytes:
        """Read one range while enforcing the shared source-read budget."""
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise RasterContractError("Range offset must be a non-negative integer.")
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise RasterContractError("Range length must be a positive integer.")
        if length > self.max_range_bytes:
            raise SourceLimitExceeded("Raster range exceeds the per-request byte budget.")
        if self.request_count + 1 > self.max_requests:
            raise SourceLimitExceeded("Raster source exceeded its cumulative request budget.")
        if self.bytes_requested + length > self.max_total_bytes:
            raise SourceLimitExceeded("Raster source exceeded its cumulative byte budget.")

        self.request_count += 1
        self.bytes_requested += length
        payload = self.adapter.read_range(
            self.reference,
            offset=offset,
            length=length,
            max_range_bytes=self.max_range_bytes,
        )
        if not isinstance(payload, bytes) or len(payload) != length:
            raise RasterContractError("Range adapter did not return the exact requested bytes.")
        return payload
