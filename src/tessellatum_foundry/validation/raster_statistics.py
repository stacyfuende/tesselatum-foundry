"""Independent output critic for raster.band_statistics results."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS
from pyproj.exceptions import CRSError


@dataclass(frozen=True)
class RasterOutputFinding:
    code: str
    status: str
    severity: str
    message: str
    json_pointer: str


@dataclass(frozen=True)
class RasterOutputInspection:
    findings: tuple[RasterOutputFinding, ...]

    @property
    def passed(self) -> bool:
        return all(finding.status == "passed" for finding in self.findings)


def inspect_raster_band_statistics_output(
    *,
    input_raster_bytes: bytes,
    output: Any,
    requested_bands: Sequence[int] | None = None,
) -> RasterOutputInspection:
    """Recompute source-derived facts and compare them with a worker result.

    This critic does not call the capability kernel. It independently opens the
    source raster, derives the expected statistics, and checks the returned
    dimensions, CRS, band selection, metadata, counts, and numeric values.
    """
    findings: list[RasterOutputFinding] = []

    def add(code: str, passed: bool, message: str, pointer: str) -> None:
        findings.append(
            RasterOutputFinding(
                code=code,
                status="passed" if passed else "failed",
                severity="info" if passed else "error",
                message=message,
                json_pointer=pointer,
            )
        )

    if not isinstance(output, Mapping):
        add("raster_output.object", False, "Output must be an object.", "/")
        return RasterOutputInspection(tuple(findings))
    statistics = output.get("statistics")
    output_crs = output.get("crs")
    if not isinstance(statistics, Mapping):
        add(
            "raster_output.statistics_object",
            False,
            "Output statistics must be an object.",
            "/statistics",
        )
        return RasterOutputInspection(tuple(findings))
    if not isinstance(output_crs, Mapping) or not isinstance(output_crs.get("wkt"), str):
        add("raster_output.crs", False, "Output must include CRS WKT.", "/crs")
        return RasterOutputInspection(tuple(findings))

    try:
        with rasterio.MemoryFile(input_raster_bytes) as memory_file:
            with memory_file.open() as dataset:
                source_crs = dataset.crs
                reported_crs = CRS.from_wkt(output_crs["wkt"])
                crs_matches = source_crs is not None and CRS.from_user_input(
                    source_crs
                ).equals(reported_crs, ignore_axis_order=True)
                add(
                    "raster_output.crs_matches_source",
                    crs_matches,
                    "Reported CRS matches the source raster."
                    if crs_matches
                    else "Reported CRS differs from the source raster.",
                    "/crs/wkt",
                )
                dimensions_match = (
                    type(statistics.get("width")) is int
                    and statistics.get("width") == dataset.width
                    and type(statistics.get("height")) is int
                    and statistics.get("height") == dataset.height
                )
                add(
                    "raster_output.dimensions",
                    dimensions_match,
                    "Reported dimensions match the source raster."
                    if dimensions_match
                    else "Reported dimensions differ from the source raster.",
                    "/statistics",
                )

                if requested_bands is None:
                    expected_indexes = list(range(1, dataset.count + 1))
                    request_selection_valid = True
                else:
                    request_selection_valid = (
                        isinstance(requested_bands, Sequence)
                        and not isinstance(requested_bands, (str, bytes))
                        and len(requested_bands) > 0
                        and all(
                            type(index) is int and 1 <= index <= dataset.count
                            for index in requested_bands
                        )
                        and len(set(requested_bands)) == len(requested_bands)
                    )
                    expected_indexes = list(requested_bands) if request_selection_valid else []
                add(
                    "raster_output.requested_band_selection",
                    request_selection_valid,
                    "Requested band selection is valid."
                    if request_selection_valid
                    else "Requested band selection is invalid.",
                    "/parameters/bands",
                )
                bands = statistics.get("bands")
                if not isinstance(bands, list) or not bands:
                    add(
                        "raster_output.band_list",
                        False,
                        "Output must contain at least one band result.",
                        "/statistics/bands",
                    )
                    return RasterOutputInspection(tuple(findings))
                indexes = [item.get("band") if isinstance(item, Mapping) else None for item in bands]
                indexes_valid = (
                    all(type(index) is int and 1 <= index <= dataset.count for index in indexes)
                    and len(set(indexes)) == len(indexes)
                )
                selection_matches_request = indexes == expected_indexes
                add(
                    "raster_output.band_selection_matches_request",
                    selection_matches_request,
                    "Returned band indexes match the requested selection."
                    if selection_matches_request
                    else "Returned band indexes differ from the requested selection.",
                    "/statistics/bands",
                )
                add(
                    "raster_output.band_indexes",
                    indexes_valid,
                    "Band indexes are unique, valid, and 1-based."
                    if indexes_valid
                    else "Band indexes are invalid or duplicated.",
                    "/statistics/bands",
                )
                add(
                    "raster_output.selected_band_count",
                    type(statistics.get("selected_band_count")) is int
                    and statistics.get("selected_band_count") == len(bands),
                    "Selected band count matches the result list."
                    if statistics.get("selected_band_count") == len(bands)
                    else "Selected band count does not match the result list.",
                    "/statistics/selected_band_count",
                )
                add(
                    "raster_output.value_semantics",
                    statistics.get("value_semantics") == "raw_stored_samples"
                    and statistics.get("standard_deviation") == "population",
                    "Output declares raw stored values and population standard deviation."
                    if statistics.get("value_semantics") == "raw_stored_samples"
                    and statistics.get("standard_deviation") == "population"
                    else "Output value or standard-deviation semantics are incorrect.",
                    "/statistics",
                )

                numeric_fields = (
                    "minimum",
                    "maximum",
                    "mean",
                    "standard_deviation",
                )
                numeric_results_match = True
                pixel_counts_match = True
                band_metadata_match = True
                for position, band_result in enumerate(bands):
                    if not isinstance(band_result, Mapping) or not indexes_valid:
                        numeric_results_match = False
                        pixel_counts_match = False
                        band_metadata_match = False
                        continue
                    band_index = indexes[position]
                    # Deliberately recompute independently from source blocks;
                    # do not call the capability kernel from this critic.
                    count = 0
                    mean = 0.0
                    m2 = 0.0
                    minimum = math.inf
                    maximum = -math.inf
                    for _, window in dataset.block_windows(band_index):
                        masked = dataset.read(band_index, window=window, masked=True)
                        values = masked.compressed().astype(np.float64, copy=False)
                        values = values[np.isfinite(values)]
                        if values.size == 0:
                            continue
                        batch_count = int(values.size)
                        batch_mean = float(np.mean(values, dtype=np.float64))
                        centered = values - batch_mean
                        batch_m2 = float(np.dot(centered, centered))
                        if count == 0:
                            count, mean, m2 = batch_count, batch_mean, batch_m2
                        else:
                            combined = count + batch_count
                            delta = batch_mean - mean
                            m2 += batch_m2 + delta * delta * count * batch_count / combined
                            mean += delta * batch_count / combined
                            count = combined
                        minimum = min(minimum, float(np.min(values)))
                        maximum = max(maximum, float(np.max(values)))
                    if count == 0:
                        numeric_results_match = False
                        pixel_counts_match = False
                        band_metadata_match = False
                        continue
                    standard_deviation = math.sqrt(max(0.0, m2 / count))
                    pixel_counts_match = (
                        pixel_counts_match
                        and type(band_result.get("valid_pixel_count")) is int
                        and band_result.get("valid_pixel_count") == count
                    )
                    expected = {
                        "minimum": minimum,
                        "maximum": maximum,
                        "mean": mean,
                        "standard_deviation": standard_deviation,
                    }
                    for field in numeric_fields:
                        actual = band_result.get(field)
                        if (
                            isinstance(actual, bool)
                            or not isinstance(actual, (int, float))
                            or not math.isfinite(actual)
                            or not math.isclose(
                                float(actual),
                                expected[field],
                                rel_tol=1e-12,
                                abs_tol=1e-12,
                            )
                        ):
                            numeric_results_match = False
                    band_metadata_match = (
                        band_metadata_match
                        and band_result.get("dtype") == dataset.dtypes[band_index - 1]
                        and band_result.get("scale") == float(dataset.scales[band_index - 1])
                        and band_result.get("offset") == float(dataset.offsets[band_index - 1])
                        and band_result.get("unit") == dataset.units[band_index - 1]
                    )
                add(
                    "raster_output.valid_pixel_counts",
                    pixel_counts_match,
                    "Valid-pixel counts match the source raster."
                    if pixel_counts_match
                    else "One or more valid-pixel counts differ from the source raster.",
                    "/statistics/bands",
                )
                add(
                    "raster_output.numeric_statistics",
                    numeric_results_match,
                    "Reported statistics match a full recomputation."
                    if numeric_results_match
                    else "Reported statistics are non-finite or differ from recomputation.",
                    "/statistics/bands",
                )
                add(
                    "raster_output.band_metadata",
                    band_metadata_match,
                    "Band dtype, scale, offset, and unit metadata are preserved."
                    if band_metadata_match
                    else "Band metadata differs from the source raster.",
                    "/statistics/bands",
                )
    except (OSError, ValueError, TypeError, CRSError, rasterio.errors.RasterioError) as error:
        add(
            "raster_output.source_readable",
            False,
            f"Source raster or reported CRS could not be independently inspected: {error}",
            "/",
        )
    return RasterOutputInspection(tuple(findings))
