"""Numeric comparison of aligned raster-window Artifacts."""

from __future__ import annotations

import math
import struct
from typing import Any

from tessellatum_foundry.storage.raster_window import (
    RasterWindowArtifact,
    RasterWindowArtifactError,
    decode_raster_window_artifact,
)


class RasterComparisonError(ValueError):
    """Raster-window Artifacts cannot be compared under the declared alignment."""


_FORMATS = {
    "uint8": "B", "int8": "b",
    "uint16": "H", "int16": "h",
    "uint32": "I", "int32": "i",
    "uint64": "Q", "int64": "q",
    "float32": "f", "float64": "d",
}


def _decode_samples(artifact: RasterWindowArtifact) -> tuple[list[list[float]], int]:
    header = artifact.header
    dtypes = header.get("dtypes")
    bands = header.get("bands")
    window = header.get("window")
    if not isinstance(dtypes, list) or not isinstance(bands, list) or len(dtypes) != len(bands):
        raise RasterComparisonError("Artifact band and dtype declarations are inconsistent.")
    if not isinstance(window, dict):
        raise RasterComparisonError("Artifact window declaration is missing.")
    count = window.get("width", 0) * window.get("height", 0)
    byte_order = header.get("byte_order")
    if byte_order not in {"little", "big"}:
        raise RasterComparisonError("Artifact byte order is invalid.")
    endian = "<" if byte_order == "little" else ">"
    widths = []
    formats = []
    for dtype in dtypes:
        if dtype not in _FORMATS:
            raise RasterComparisonError(f"Unsupported comparison dtype: {dtype!r}")
        formats.append(endian + _FORMATS[dtype])
        widths.append(struct.calcsize(_FORMATS[dtype]))
    pixel_stride = sum(widths)
    if len(artifact.samples) != count * pixel_stride:
        raise RasterComparisonError("Sample bytes do not match declared pixel grid.")
    band_values = [[] for _ in bands]
    for pixel in range(count):
        cursor = pixel * pixel_stride
        for index, fmt in enumerate(formats):
            band_values[index].append(float(struct.unpack_from(fmt, artifact.samples, cursor)[0]))
            cursor += widths[index]
    return band_values, count


def _metrics(values_a: list[float], values_b: list[float]) -> dict[str, Any]:
    n = len(values_a)
    differences = [b - a for a, b in zip(values_a, values_b)]
    absolute = [abs(d) for d in differences]
    squared = [d * d for d in differences]
    bias = sum(differences) / n
    mae = sum(absolute) / n
    rmse = math.sqrt(sum(squared) / n)
    max_abs = max(absolute)
    mean_a = sum(values_a) / n
    mean_b = sum(values_b) / n
    centered_a = [x - mean_a for x in values_a]
    centered_b = [x - mean_b for x in values_b]
    denom = math.sqrt(sum(x * x for x in centered_a) * sum(x * x for x in centered_b))
    correlation = sum(x * y for x, y in zip(centered_a, centered_b)) / denom if denom else None
    return {
        "n": n,
        "bias_b_minus_a": bias,
        "mean_absolute_error": mae,
        "root_mean_square_error": rmse,
        "maximum_absolute_difference": max_abs,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "correlation": correlation,
    }


def compare_raster_window_artifacts(
    artifact_a: RasterWindowArtifact | bytes,
    artifact_b: RasterWindowArtifact | bytes,
) -> dict[str, Any]:
    """Compare two aligned numeric raster windows on their shared valid pixels.

    No resampling, reprojection, or implicit grid matching is performed.
    """
    try:
        a = decode_raster_window_artifact(artifact_a) if isinstance(artifact_a, bytes) else artifact_a
        b = decode_raster_window_artifact(artifact_b) if isinstance(artifact_b, bytes) else artifact_b
    except RasterWindowArtifactError as error:
        raise RasterComparisonError(f"Invalid raster-window Artifact: {error}") from error
    ha, hb = a.header, b.header
    if ha.get("window") != hb.get("window"):
        raise RasterComparisonError("Raster windows differ; comparison requires identical pixel windows.")
    ga, gb = ha.get("grid", {}), hb.get("grid", {})
    if ga.get("crs") != gb.get("crs") or ga.get("transform") != gb.get("transform"):
        raise RasterComparisonError("Raster grids differ; comparison requires identical CRS and transform.")
    if ha.get("bands") != hb.get("bands"):
        raise RasterComparisonError("Band selections differ; bands must match in order.")
    if ha.get("pixel_interleave") != "pixel" or hb.get("pixel_interleave") != "pixel":
        raise RasterComparisonError("Only pixel-interleaved raster-window Artifacts are supported.")
    if len(a.validity) != len(b.validity):
        raise RasterComparisonError("Validity masks have different lengths.")
    va, count = _decode_samples(a)
    vb, count_b = _decode_samples(b)
    if count != count_b:
        raise RasterComparisonError("Raster pixel counts differ.")
    shared = [i for i, (valid_a, valid_b) in enumerate(zip(a.validity, b.validity)) if valid_a and valid_b]
    if not shared:
        raise RasterComparisonError("No pixels are valid in both artifacts.")
    results = []
    for band_index, band_id in enumerate(ha["bands"]):
        aa = [va[band_index][i] for i in shared]
        bb = [vb[band_index][i] for i in shared]
        if not all(math.isfinite(x) for x in aa + bb):
            raise RasterComparisonError("Non-finite samples are not supported in numeric comparison.")
        results.append({"band": band_id, **_metrics(aa, bb)})
    return {
        "comparison": "raster-window-numeric",
        "comparison_version": "1.0.0",
        "alignment": "exact-grid",
        "pixel_count": count,
        "valid_a": sum(a.validity),
        "valid_b": sum(b.validity),
        "valid_both": len(shared),
        "valid_only_a": sum(x and not y for x, y in zip(a.validity, b.validity)),
        "valid_only_b": sum(y and not x for x, y in zip(a.validity, b.validity)),
        "bands": results,
    }
