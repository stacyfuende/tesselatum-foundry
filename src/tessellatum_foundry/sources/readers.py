"""Incremental readers for simple spatial interchange formats."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from typing import Any


class FeatureReaderError(ValueError):
    """Raised when a byte stream cannot be decoded as valid spatial features."""


class NdjsonFeatureReader:
    """Read one GeoJSON Feature per newline without buffering the whole source."""

    supported_media_types = ("application/x-ndjson", "application/ndjson")

    def __init__(self, *, max_feature_bytes: int = 8 * 1024 * 1024) -> None:
        if (
            isinstance(max_feature_bytes, bool)
            or not isinstance(max_feature_bytes, int)
            or max_feature_bytes < 1
        ):
            raise ValueError("max_feature_bytes must be a positive integer.")
        self.max_feature_bytes = max_feature_bytes

    def iter_features(
        self,
        chunks: Iterable[bytes],
        *,
        selection: Mapping[str, object],
    ) -> Iterator[Mapping[str, Any]]:
        """Decode NDJSON records incrementally, preserving their source order.

        This initial reader does not implement spatial or attribute filtering.
        Non-empty selection is rejected so a caller cannot assume it was applied.
        """
        if selection:
            raise FeatureReaderError(
                "NDJSON reader does not support source selection or query pushdown."
            )

        pending = bytearray()
        offset = 0
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                raise FeatureReaderError("Source adapters must yield byte chunks.")
            pending.extend(chunk)
            while True:
                boundary = pending.find(b"\n")
                if boundary < 0:
                    break
                line = bytes(pending[:boundary]).rstrip(b"\r")
                del pending[: boundary + 1]
                if line.strip():
                    yield self._decode_feature(line, offset)
                    offset += 1
            if len(pending) > self.max_feature_bytes:
                raise FeatureReaderError(
                    f"NDJSON record at offset {offset} exceeds "
                    f"the {self.max_feature_bytes}-byte feature limit."
                )

        final_line = bytes(pending).rstrip(b"\r")
        if final_line.strip():
            yield self._decode_feature(final_line, offset)

    def _decode_feature(self, line: bytes, offset: int) -> Mapping[str, Any]:
        if len(line) > self.max_feature_bytes:
            raise FeatureReaderError(
                f"NDJSON record at offset {offset} exceeds "
                f"the {self.max_feature_bytes}-byte feature limit."
            )
        try:
            feature = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FeatureReaderError(
                f"NDJSON record at offset {offset} is not valid UTF-8 JSON."
            ) from error
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise FeatureReaderError(
                f"NDJSON record at offset {offset} is not a GeoJSON Feature."
            )
        return feature
