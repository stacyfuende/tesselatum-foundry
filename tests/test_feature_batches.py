from __future__ import annotations

import hashlib
import json

import pytest

from tessellatum_foundry.sources.batches import (
    FeatureBatchError,
    FeatureExceedsBatchLimit,
    iter_feature_batches,
)


def feature(index: int) -> dict:
    return {
        "type": "Feature",
        "id": index,
        "geometry": {"type": "Point", "coordinates": [index, index]},
        "properties": {"index": index},
    }


def test_feature_batches_preserve_order_and_bound_feature_count() -> None:
    batches = list(
        iter_feature_batches((feature(i) for i in range(7)), max_features=3, max_bytes=4096)
    )

    assert [batch.sequence for batch in batches] == [0, 1, 2]
    assert [batch.first_feature_offset for batch in batches] == [0, 3, 6]
    assert [batch.feature_count for batch in batches] == [3, 3, 1]
    decoded = [json.loads(batch.payload)["features"] for batch in batches]
    assert [item["id"] for batch in decoded for item in batch] == list(range(7))


def test_feature_batches_enforce_encoded_byte_limit() -> None:
    batches = list(
        iter_feature_batches((feature(i) for i in range(5)), max_features=100, max_bytes=220)
    )

    assert len(batches) > 1
    assert all(batch.byte_size <= 220 for batch in batches)


def test_feature_batches_checksum_covers_exact_worker_payload() -> None:
    batch = next(iter_feature_batches([feature(1)], max_bytes=4096))

    assert batch.checksum_sha256 == hashlib.sha256(batch.payload).hexdigest()


def test_feature_batch_rejects_single_feature_larger_than_limit() -> None:
    large = feature(1)
    large["properties"]["description"] = "x" * 500

    with pytest.raises(FeatureExceedsBatchLimit):
        list(iter_feature_batches([large], max_bytes=256))


def test_feature_batch_rejects_non_feature_items() -> None:
    with pytest.raises(FeatureBatchError, match="GeoJSON Feature"):
        list(iter_feature_batches([{"type": "FeatureCollection", "features": []}]))


def test_feature_batch_rejects_non_finite_json_values() -> None:
    invalid = feature(1)
    invalid["properties"]["measurement"] = float("nan")

    with pytest.raises(FeatureBatchError, match="valid JSON"):
        list(iter_feature_batches([invalid]))


@pytest.mark.parametrize(
    ("max_features", "max_bytes"),
    [(0, 4096), (True, 4096), (10, 0), (10, True)],
)
def test_feature_batch_rejects_invalid_limits(max_features, max_bytes) -> None:
    with pytest.raises(ValueError):
        list(
            iter_feature_batches(
                [feature(1)], max_features=max_features, max_bytes=max_bytes
            )
        )
