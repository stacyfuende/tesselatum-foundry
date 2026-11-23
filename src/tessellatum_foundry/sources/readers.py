"""Incremental readers for simple spatial interchange formats."""

from __future__ import annotations

import codecs
import json
from collections.abc import Iterable, Iterator, Mapping
from typing import Any


class FeatureReaderError(ValueError):
    """Raised when a byte stream cannot be decoded as valid spatial features."""


class _IncrementalJson:
    """Small forward-only JSON decoder with bounded token materialization."""

    def __init__(self, chunks: Iterable[bytes]) -> None:
        self._chunks = iter(chunks)
        self._utf8 = codecs.getincrementaldecoder("utf-8")("strict")
        self.buffer = ""
        self.position = 0
        self.eof = False

    def _read_more(self) -> None:
        if self.eof:
            return
        try:
            chunk = next(self._chunks)
        except StopIteration:
            self.eof = True
            try:
                self.buffer += self._utf8.decode(b"", final=True)
            except UnicodeDecodeError as error:
                raise FeatureReaderError("Source is not valid UTF-8.") from error
            return
        if not isinstance(chunk, bytes):
            raise FeatureReaderError("Source adapters must yield byte chunks.")
        try:
            # Decode in slices so a large adapter chunk is not duplicated into
            # one equally large text allocation.
            for start in range(0, len(chunk), 64 * 1024):
                self.buffer += self._utf8.decode(chunk[start : start + 64 * 1024])
        except UnicodeDecodeError as error:
            raise FeatureReaderError("Source is not valid UTF-8.") from error

    def _compact(self) -> None:
        if self.position >= 64 * 1024:
            self.buffer = self.buffer[self.position :]
            self.position = 0

    def skip_ws(self) -> None:
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position] in " \t\r\n":
                self.position += 1
            self._compact()
            if self.position < len(self.buffer) or self.eof:
                return
            self._read_more()

    def expect(self, expected: str) -> None:
        self.skip_ws()
        while self.position >= len(self.buffer) and not self.eof:
            self._read_more()
            self.skip_ws()
        if self.position >= len(self.buffer) or self.buffer[self.position] != expected:
            raise FeatureReaderError(f"Expected {expected!r} in GeoJSON FeatureCollection.")
        self.position += 1

    def value(self, *, max_bytes: int, label: str) -> Any:
        """Decode exactly one JSON value, retrying only when input is incomplete."""
        start = self.position
        while True:
            try:
                value, end = json.JSONDecoder().raw_decode(self.buffer, start)
                consumed = self.buffer[start:end]
                if len(consumed.encode("utf-8")) > max_bytes:
                    raise FeatureReaderError(
                        f"{label} exceeds the configured {max_bytes}-byte limit."
                    )
                self.position = end
                return value
            except json.JSONDecodeError as error:
                pending = self.buffer[start:]
                if len(pending.encode("utf-8")) > max_bytes:
                    raise FeatureReaderError(
                        f"{label} exceeds the configured {max_bytes}-byte limit."
                    ) from error
                # An error before the final buffered character cannot be fixed
                # by appending more bytes and is therefore malformed JSON.
                if self.eof or error.pos < len(self.buffer) - 1:
                    raise FeatureReaderError(f"{label} is malformed JSON.") from error
                self._read_more()


class GeoJsonFeatureCollectionReader:
    """Incrementally read a GeoJSON FeatureCollection one bounded feature at a time.

    Only the current feature is materialized. The input envelope and each
    feature are decoded independently; feature bytes are limited before
    yielding. Unknown top-level members are skipped as bounded JSON values.
    """

    supported_media_types = (
        "application/vnd.tessellatum.spatial-feature-collection+json",
        "application/geo+json",
    )

    def __init__(
        self,
        *,
        max_feature_bytes: int = 8 * 1024 * 1024,
        max_member_bytes: int = 64 * 1024,
    ) -> None:
        for name, value in (
            ("max_feature_bytes", max_feature_bytes),
            ("max_member_bytes", max_member_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        self.max_feature_bytes = max_feature_bytes
        self.max_member_bytes = max_member_bytes

    def iter_features(
        self,
        chunks: Iterable[bytes],
        *,
        selection: Mapping[str, object],
    ) -> Iterator[Mapping[str, Any]]:
        if selection:
            raise FeatureReaderError(
                "GeoJSON FeatureCollection reader does not support source selection "
                "or query pushdown."
            )

        source = _IncrementalJson(chunks)
        source.expect("{")
        seen: set[str] = set()
        collection_type: Any = None
        feature_count = 0
        source.skip_ws()
        if source.position < len(source.buffer) and source.buffer[source.position] == "}":
            raise FeatureReaderError("GeoJSON object is missing type and features members.")

        while True:
            key = source.value(max_bytes=1024, label="FeatureCollection member name")
            if not isinstance(key, str):
                raise FeatureReaderError("FeatureCollection member names must be strings.")
            if key in seen:
                raise FeatureReaderError(f"Duplicate FeatureCollection member {key!r}.")
            seen.add(key)
            source.expect(":")
            if key == "type":
                collection_type = source.value(
                    max_bytes=128, label="FeatureCollection type"
                )
            elif key == "features":
                source.expect("[")
                source.skip_ws()
                if source.position < len(source.buffer) and source.buffer[source.position] == "]":
                    source.position += 1
                else:
                    while True:
                        feature = source.value(
                            max_bytes=self.max_feature_bytes,
                            label=f"Feature at offset {feature_count}",
                        )
                        if not isinstance(feature, dict) or feature.get("type") != "Feature":
                            raise FeatureReaderError(
                                f"Item at offset {feature_count} is not a GeoJSON Feature."
                            )
                        yield feature
                        feature_count += 1
                        source.skip_ws()
                        if source.position < len(source.buffer) and source.buffer[source.position] == ",":
                            source.position += 1
                            continue
                        source.expect("]")
                        break
            else:
                source.value(
                    max_bytes=self.max_member_bytes,
                    label=f"FeatureCollection member {key!r}",
                )

            source.skip_ws()
            if source.position < len(source.buffer) and source.buffer[source.position] == ",":
                source.position += 1
                continue
            source.expect("}")
            break

        if collection_type != "FeatureCollection" or "features" not in seen:
            raise FeatureReaderError(
                "GeoJSON input must be a FeatureCollection with type and features members."
            )
        source.skip_ws()
        if source.position < len(source.buffer):
            raise FeatureReaderError("Unexpected content after GeoJSON FeatureCollection.")
        while not source.eof:
            source._read_more()
            source.skip_ws()
            if source.position < len(source.buffer):
                raise FeatureReaderError(
                    "Unexpected content after GeoJSON FeatureCollection."
                )


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
        """Decode NDJSON records incrementally, preserving their source order."""
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
                boundary = pending.find(b"\\n")
                if boundary < 0:
                    break
                line = bytes(pending[:boundary]).rstrip(b"\\r")
                del pending[: boundary + 1]
                if line.strip():
                    yield self._decode_feature(line, offset)
                    offset += 1
            if len(pending) > self.max_feature_bytes:
                raise FeatureReaderError(
                    f"NDJSON record at offset {offset} exceeds "
                    f"the {self.max_feature_bytes}-byte feature limit."
                )

        final_line = bytes(pending).rstrip(b"\\r")
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
