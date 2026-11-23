from __future__ import annotations

import hashlib
import json

import pytest

from tessellatum_foundry.execution.batches import (
    BatchExecutionError,
    VectorBufferBatchExecutor,
)
from tessellatum_foundry.execution.protocol import WorkerResult
from tessellatum_foundry.sources.batches import FeatureBatch


def collection(count: int) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": index,
                "geometry": {"type": "Point", "coordinates": [index, index]},
                "properties": {"index": index},
            }
            for index in range(count)
        ],
    }


def batch_for(count: int = 2) -> FeatureBatch:
    payload = json.dumps(
        collection(count), sort_keys=True, separators=(",", ":")
    ).encode()
    return FeatureBatch(
        sequence=3,
        first_feature_offset=6,
        feature_count=count,
        payload=payload,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )


class FakeWorker:
    capability_id = "vector.buffer"
    capability_version = "1.0.0"
    implementation_id = "vector-buffer-test"
    implementation_version = "1.0.0"
    worker_id = "test-worker"
    worker_type = "local_docker"

    def __init__(self, output_count: int = 2, digest: str = "sha256:" + "a" * 64):
        self.output_count = output_count
        self.digest = digest
        self.calls = 0

    def execute(self, *, input_bytes, capability_version, input_crs,
                measurement_crs, parameters, runtime_image_digest=None):
        self.calls += 1
        return WorkerResult(
            feature_collection=collection(self.output_count),
            crs=input_crs,
            duration_ms=12,
            runtime_image_digest=self.digest,
        )

    def image_digest(self):
        return self.digest


def execute(executor, batch):
    return executor.execute(
        batch,
        capability_version="1.0.0",
        input_crs={"authority": "EPSG", "code": "3857"},
        measurement_crs={"authority": "EPSG", "code": "3857"},
        parameters={"distance": 10, "unit": "metre"},
        runtime_image_digest="sha256:" + "a" * 64,
    )


def test_batch_executor_preserves_offsets_and_checksums() -> None:
    worker = FakeWorker()
    result = execute(VectorBufferBatchExecutor(worker), batch_for())

    assert result.sequence == 3
    assert result.first_feature_offset == 6
    assert result.feature_count == 2
    assert result.input_checksum_sha256 == batch_for().checksum_sha256
    assert result.output_crs == {"authority": "EPSG", "code": "3857"}
    assert hashlib.sha256(result.payload).hexdigest() == result.output_checksum_sha256
    assert result.duration_ms == 12
    assert worker.calls == 1


def test_batch_executor_rejects_tampered_input_before_worker_call() -> None:
    batch = batch_for()
    tampered = FeatureBatch(
        sequence=batch.sequence,
        first_feature_offset=batch.first_feature_offset,
        feature_count=batch.feature_count,
        payload=batch.payload + b" ",
        checksum_sha256=batch.checksum_sha256,
    )
    worker = FakeWorker()

    with pytest.raises(BatchExecutionError, match="checksum"):
        execute(VectorBufferBatchExecutor(worker), tampered)

    assert worker.calls == 0


def test_batch_executor_rejects_feature_count_mismatch() -> None:
    worker = FakeWorker(output_count=1)

    with pytest.raises(BatchExecutionError, match="feature count"):
        execute(VectorBufferBatchExecutor(worker), batch_for(2))


def test_batch_executor_rejects_unpinned_worker_image() -> None:
    worker = FakeWorker(digest="sha256:" + "b" * 64)

    with pytest.raises(BatchExecutionError, match="digest"):
        execute(VectorBufferBatchExecutor(worker), batch_for())


def test_batch_executor_rejects_batch_metadata_mismatch() -> None:
    batch = batch_for()
    malformed = FeatureBatch(
        sequence=batch.sequence,
        first_feature_offset=batch.first_feature_offset,
        feature_count=99,
        payload=batch.payload,
        checksum_sha256=batch.checksum_sha256,
    )
    worker = FakeWorker()

    with pytest.raises(BatchExecutionError, match="metadata"):
        execute(VectorBufferBatchExecutor(worker), malformed)

    assert worker.calls == 0


def test_batch_executor_rejects_boolean_sequence_metadata() -> None:
    batch = batch_for()
    malformed = FeatureBatch(
        sequence=True,
        first_feature_offset=batch.first_feature_offset,
        feature_count=batch.feature_count,
        payload=batch.payload,
        checksum_sha256=batch.checksum_sha256,
    )
    worker = FakeWorker()

    with pytest.raises(BatchExecutionError, match="sequence"):
        execute(VectorBufferBatchExecutor(worker), malformed)

    assert worker.calls == 0
