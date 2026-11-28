from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pytest

from tessellatum_foundry.storage.streaming import (
    StreamingFeatureCollectionTransaction,
    StreamingTransactionError,
)


@dataclass
class Batch:
    sequence: int
    first_feature_offset: int
    feature_count: int
    payload: bytes
    output_checksum_sha256: str


def batch(sequence: int, offset: int, features: list[dict]) -> Batch:
    payload = json.dumps(
        {"type": "FeatureCollection", "features": features},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return Batch(sequence, offset, len(features), payload, hashlib.sha256(payload).hexdigest())


def test_streaming_transaction_stages_and_seals_without_publishing_artifact(tmp_path):
    transaction = StreamingFeatureCollectionTransaction(
        tmp_path, run_id="run:stream", attempt=1,
        max_output_bytes=100_000, max_batches=10,
    )
    transaction.append(
        batch(0, 0, [{"type": "Feature", "properties": {"id": 1}, "geometry": None}])
    )
    transaction.append(
        batch(1, 1, [{"type": "Feature", "properties": {"id": 2}, "geometry": None}])
    )

    with pytest.raises(StreamingTransactionError, match="EOF"):
        transaction.seal_input({"eof_verified": False})
    transaction.seal_input({"eof_verified": True, "source_version": "v1"})
    sealed = transaction.seal_output()

    document = json.loads(transaction.payload_path.read_bytes())
    assert len(document["features"]) == 2
    assert sealed["feature_count"] == 2
    assert sealed["state"] == "output_sealed"
    actual_checksum = hashlib.sha256(transaction.payload_path.read_bytes()).hexdigest()
    assert sealed["output_checksum_sha256"] == actual_checksum
    assert not list((tmp_path / "objects").rglob("*")) if (tmp_path / "objects").exists() else True

    validated = transaction.mark_validated({"passed": True, "critic": "test"})
    assert validated["state"] == "validated"
    assert json.loads(transaction.journal_path.read_text())["state"] == "validated"


def test_streaming_transaction_rejects_reordered_or_duplicate_batches(tmp_path):
    transaction = StreamingFeatureCollectionTransaction(
        tmp_path, run_id="run:order", attempt=1,
        max_output_bytes=100_000, max_batches=10,
    )
    with pytest.raises(StreamingTransactionError, match="contiguous"):
        transaction.append(batch(1, 0, [{"type": "Feature", "properties": {}, "geometry": None}]))
    transaction.append(batch(0, 0, [{"type": "Feature", "properties": {}, "geometry": None}]))
    with pytest.raises(StreamingTransactionError, match="contiguous"):
        transaction.append(batch(0, 0, [{"type": "Feature", "properties": {}, "geometry": None}]))
    transaction.abort("test.cancelled")
    assert json.loads(transaction.journal_path.read_text())["state"] == "aborted"


def test_streaming_transaction_rejects_tampered_batch_and_wrong_count(tmp_path):
    transaction = StreamingFeatureCollectionTransaction(
        tmp_path, run_id="run:integrity", attempt=1,
        max_output_bytes=100_000, max_batches=10,
    )
    valid = batch(0, 0, [{"type": "Feature", "properties": {}, "geometry": None}])
    valid.payload += b" "
    with pytest.raises(StreamingTransactionError, match="checksum"):
        transaction.append(valid)

    invalid = batch(0, 0, [{"type": "Feature", "properties": {}, "geometry": None}])
    invalid.feature_count = 2
    with pytest.raises(StreamingTransactionError, match="feature count"):
        transaction.append(invalid)
    transaction.abort("test.invalid_input")


def test_streaming_transaction_enforces_limits_and_validation_gate(tmp_path):
    transaction = StreamingFeatureCollectionTransaction(
        tmp_path, run_id="run:limits", attempt=1,
        max_output_bytes=80, max_batches=1,
    )
    feature = {"type": "Feature", "properties": {"long": "x" * 200}, "geometry": None}
    with pytest.raises(StreamingTransactionError, match="byte limit"):
        transaction.append(batch(0, 0, [feature]))
    with pytest.raises(StreamingTransactionError, match="expected 'output_sealed'"):
        transaction.mark_validated({"passed": True})
    transaction.abort("test.limit")
