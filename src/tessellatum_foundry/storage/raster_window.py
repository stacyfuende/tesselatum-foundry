"""Versioned binary envelope for Foundry raster-window Artifacts.

This container is deliberately not GeoTIFF/COG. It preserves raw sample bytes,
an explicit packed validity mask, and canonical JSON grid/provenance metadata.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any, Mapping

from tessellatum_foundry.sources.window_assembly import RasterWindowBuffer


_MAGIC = b"TFRW\x00\x01\r\n"
_PREFIX = struct.Struct(">8sI")
_MAX_HEADER_BYTES = 1024 * 1024
_DTYPE_BYTES = {
    "uint8": 1, "int8": 1, "uint16": 2, "int16": 2,
    "uint32": 4, "int32": 4, "uint64": 8, "int64": 8,
    "float32": 4, "float64": 8,
}


class RasterWindowArtifactError(ValueError):
    """A raster-window Artifact envelope is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class RasterWindowArtifact:
    """Decoded envelope; samples remain in their declared TIFF byte order."""

    header: dict[str, Any]
    samples: bytes
    validity: tuple[bool, ...]


def _pack_validity(validity: tuple[bool, ...]) -> bytes:
    packed = bytearray((len(validity) + 7) // 8)
    for index, valid in enumerate(validity):
        if not isinstance(valid, bool):
            raise RasterWindowArtifactError("Validity entries must be booleans.")
        if valid:
            packed[index // 8] |= 1 << (index % 8)
    return bytes(packed)


def encode_raster_window_artifact(
    buffer: RasterWindowBuffer,
    *,
    validity: tuple[bool, ...],
    grid: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> bytes:
    """Encode raw samples, validity and JSON metadata into a deterministic envelope."""
    pixel_count = buffer.window.width * buffer.window.height
    if len(validity) != pixel_count:
        raise RasterWindowArtifactError("Validity mask must contain one value per pixel.")
    if not buffer.bands or len(buffer.bands) != len(buffer.dtypes):
        raise RasterWindowArtifactError("Selected bands and dtypes must align.")
    try:
        expected_bytes = pixel_count * sum(_DTYPE_BYTES[dtype] for dtype in buffer.dtypes)
    except KeyError as error:
        raise RasterWindowArtifactError("Unsupported raster sample dtype.") from error
    if len(buffer.samples) != expected_bytes:
        raise RasterWindowArtifactError("Sample byte length does not match the declared window.")
    if buffer.byte_order not in {"little", "big"}:
        raise RasterWindowArtifactError("Sample byte order must be little or big.")

    header = {
        "format": "tessellatum-raster-window",
        "format_version": "1.0.0",
        "window": {
            "row_offset": buffer.window.row_offset,
            "column_offset": buffer.window.column_offset,
            "height": buffer.window.height,
            "width": buffer.window.width,
        },
        "bands": list(buffer.bands),
        "dtypes": list(buffer.dtypes),
        "byte_order": buffer.byte_order,
        "pixel_interleave": "pixel",
        "sample_bytes": len(buffer.samples),
        "pixel_count": pixel_count,
        "validity_encoding": "bitset-lsb0",
        "validity_bytes": (pixel_count + 7) // 8,
        "grid": dict(grid),
        "provenance": dict(provenance),
    }
    try:
        header_bytes = json.dumps(
            header, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RasterWindowArtifactError("Grid and provenance metadata must be finite JSON data.") from error
    if len(header_bytes) > _MAX_HEADER_BYTES:
        raise RasterWindowArtifactError("Raster-window metadata header exceeds its size limit.")
    return (
        _PREFIX.pack(_MAGIC, len(header_bytes))
        + header_bytes
        + buffer.samples
        + _pack_validity(validity)
    )


def decode_raster_window_artifact(payload: bytes) -> RasterWindowArtifact:
    """Decode and strictly validate one complete Foundry raster-window envelope."""
    if not isinstance(payload, bytes) or len(payload) < _PREFIX.size:
        raise RasterWindowArtifactError("Raster-window Artifact is truncated.")
    magic, header_length = _PREFIX.unpack_from(payload)
    if magic != _MAGIC or header_length < 2 or header_length > _MAX_HEADER_BYTES:
        raise RasterWindowArtifactError("Raster-window Artifact magic or header length is invalid.")
    header_end = _PREFIX.size + header_length
    if header_end > len(payload):
        raise RasterWindowArtifactError("Raster-window Artifact header is truncated.")
    try:
        header = json.loads(payload[_PREFIX.size:header_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RasterWindowArtifactError("Raster-window Artifact header is invalid JSON.") from error
    if not isinstance(header, dict) or header.get("format") != "tessellatum-raster-window":
        raise RasterWindowArtifactError("Raster-window Artifact format identifier is invalid.")
    if header.get("format_version") != "1.0.0":
        raise RasterWindowArtifactError("Raster-window Artifact version is unsupported.")
    window = header.get("window")
    bands, dtypes = header.get("bands"), header.get("dtypes")
    if not isinstance(window, dict) or not isinstance(bands, list) or not isinstance(dtypes, list):
        raise RasterWindowArtifactError("Raster-window Artifact shape metadata is incomplete.")
    try:
        width, height = window["width"], window["height"]
        row, column = window["row_offset"], window["column_offset"]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in
               (width, height, row, column)) or min(width, height) < 1 or min(row, column) < 0:
            raise ValueError
        if not bands or len(bands) != len(dtypes):
            raise ValueError
        if any(isinstance(band, bool) or not isinstance(band, int) or band < 1 for band in bands):
            raise ValueError
        sample_length = width * height * sum(_DTYPE_BYTES[dtype] for dtype in dtypes)
    except (KeyError, TypeError, ValueError) as error:
        raise RasterWindowArtifactError("Raster-window Artifact dimensions or dtypes are invalid.") from error
    pixel_count = width * height
    validity_length = (pixel_count + 7) // 8
    if (
        header.get("sample_bytes") != sample_length
        or header.get("pixel_count") != pixel_count
        or header.get("validity_bytes") != validity_length
        or header.get("validity_encoding") != "bitset-lsb0"
        or header.get("byte_order") not in {"little", "big"}
        or header.get("pixel_interleave") != "pixel"
    ):
        raise RasterWindowArtifactError("Raster-window Artifact declared lengths or encodings are inconsistent.")
    samples_start = header_end
    validity_start = samples_start + sample_length
    expected_end = validity_start + validity_length
    if expected_end != len(payload):
        raise RasterWindowArtifactError("Raster-window Artifact payload length is inconsistent.")
    packed = payload[validity_start:expected_end]
    if pixel_count % 8 and packed and packed[-1] >> (pixel_count % 8):
        raise RasterWindowArtifactError("Raster-window validity padding bits must be zero.")
    validity = tuple(
        bool(packed[index // 8] & (1 << (index % 8)))
        for index in range(pixel_count)
    )
    return RasterWindowArtifact(
        header=header,
        samples=payload[samples_start:validity_start],
        validity=validity,
    )
