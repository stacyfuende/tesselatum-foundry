"""Bounded GeoJSON feature batches for streaming spatial execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any


class FeatureBatchError(ValueError):
    """Raised when a feature cannot be represented by the batch transport."""


class FeatureExceedsBatchLimit(FeatureBatchError):
    """Raised when one feature cannot fit within the configured batch byte limit."""


@dataclass(frozen=True, slots=True)
class FeatureBatch:
    """One bounded, canonical FeatureCollection payload.

    Offsets count source features, not bytes. The checksum covers the exact
    payload bytes sent to a worker. The batch is transport evidence, not a
    durable source snapshot or a claim that the source can be resumed.
    """

    sequence: int
    first_feature_offset: int
    feature_count: int
    payload: bytes
    checksum_sha256: str

    @property
    def byte_size(self) -> int:
        return len(self.payload)


def iter_feature_batches(
    features: Iterable[Mapping[str, Any]],
    *,
    max_features: int = 1_000,
    max_bytes: int = 8 * 1024 * 1024,
) -> Iterator[FeatureBatch]:
    """Encode a feature iterator into bounded FeatureCollection payloads.

    Only the current batch is retained. A single feature larger than max_bytes
    fails explicitly instead of being split into invalid partial JSON. Input
    order is preserved and offsets are monotonically increasing.
    """
    if isinstance(max_features, bool) or not isinstance(max_features, int) or max_features < 1:
        raise ValueError("max_features must be a positive integer.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 64:
        raise ValueError("max_bytes must be an integer of at least 64.")

    prefix = b'{"type":"FeatureCollection","features":['
    suffix = b"]}"
    batch_items: list[bytes] = []
    batch_size = len(prefix) + len(suffix)
    batch_start = 0
    feature_offset = 0
    sequence = 0

    def emit(items: list[bytes], start: int, number: int) -> FeatureBatch:
        payload = prefix + b",".join(items) + suffix
        return FeatureBatch(
            sequence=number,
            first_feature_offset=start,
            feature_count=len(items),
            payload=payload,
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
        )

    for feature in features:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise FeatureBatchError("Each streamed item must be a GeoJSON Feature object.")
        try:
            encoded = json.dumps(
                feature,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise FeatureBatchError(f"Feature at offset {feature_offset} is not valid JSON: {error}") from error

        candidate_size = batch_size + len(encoded) + (1 if batch_items else 0)
        if candidate_size > max_bytes:
            if not batch_items:
                raise FeatureExceedsBatchLimit(
                    f"Feature at offset {feature_offset} exceeds the {max_bytes}-byte batch limit."
                )
            yield emit(batch_items, batch_start, sequence)
            sequence += 1
            batch_items = []
            batch_size = len(prefix) + len(suffix)
            batch_start = feature_offset
            candidate_size = batch_size + len(encoded)

        if candidate_size > max_bytes:
            raise FeatureExceedsBatchLimit(
                f"Feature at offset {feature_offset} exceeds the {max_bytes}-byte batch limit."
            )

        batch_items.append(encoded)
        batch_size = candidate_size
        feature_offset += 1

        if len(batch_items) >= max_features:
            yield emit(batch_items, batch_start, sequence)
            sequence += 1
            batch_items = []
            batch_size = len(prefix) + len(suffix)
            batch_start = feature_offset

    if batch_items:
        yield emit(batch_items, batch_start, sequence)
