from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pytest

from tessellatum_foundry.execution.batches import ProcessedFeatureBatch
from tessellatum_foundry.execution.streaming_pipeline import StreamingVectorBufferPipeline
from tessellatum_foundry.sources.batches import FeatureBatch
from tessellatum_foundry.storage.streaming import StreamingFeatureCollectionTransaction


_DIGEST = "a" * 64
_IMAGE = "sha256:" + _DIGEST


@dataclass
class Aggregate:
    passed: bool = True
    geometry_types: tuple[str, ...] = ("Polygon",)
    runtime_image_digest: str = _IMAGE

    def as_validation_report(self, run_id: str) -> dict[str, Any]:
        return {
            "report_id": f"report:{run_id}:output",
            "subject": {"kind": "run", "id": run_id},
            "stage": "execution_output",
            "overall_status": "passed" if self.passed else "failed",
            "created_at": "2026-01-01T00:00:00Z",
            "validator": {"name": "test-stream-critic", "version": "1.0.0"},
            "findings": [],
        }


class FakeExecutor:
    def execute(self, batch: FeatureBatch, **kwargs: Any) -> ProcessedFeatureBatch:
        payload = batch.payload
        return ProcessedFeatureBatch(
            sequence=batch.sequence,
            first_feature_offset=batch.first_feature_offset,
            feature_count=batch.feature_count,
            input_checksum_sha256=batch.checksum_sha256,
            payload=payload,
            output_checksum_sha256=hashlib.sha256(payload).hexdigest(),
            output_crs={"authority": "EPSG:4326"},
            duration_ms=7,
            runtime_image_digest=kwargs["runtime_image_digest"],
        )


class FakeValidator:
    def __init__(self, aggregate: Aggregate | None = None) -> None:
        self.aggregate = aggregate or Aggregate()
        self.added = []

    def add(self, source: FeatureBatch, output: ProcessedFeatureBatch) -> None:
        self.added.append((source.sequence, output.sequence))

    def finish(self) -> Aggregate:
        return self.aggregate


class FakeRuns:
    def __init__(self) -> None:
        self.run = {
            "run_id": "run:stream-pipeline",
            "attempt": 1,
            "status": "running",
            "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
        }
        self.reports = []
        self.transitions = []

    def get_run(self, run_id: str) -> dict[str, Any]:
        assert run_id == self.run["run_id"]
        return dict(self.run)

    def save_validation_report(self, report: dict[str, Any]) -> dict[str, Any]:
        self.reports.append(report)
        return report

    def transition(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        self.transitions.append(kwargs)
        self.run["status"] = kwargs["new_status"]
        return dict(self.run)


class FakeFinalizer:
    def finalize(self, transaction: StreamingFeatureCollectionTransaction, **kwargs: Any):
        assert transaction.state == "validated"
        return type("Finalized", (), {
            "artifact": {"artifact_id": kwargs["artifact_id"]},
            "run": {"run_id": transaction.run_id, "status": "succeeded"},
        })()


def make_batch(sequence: int = 0, offset: int = 0) -> FeatureBatch:
    feature = {
        "type": "Feature",
        "id": offset,
        "properties": {"id": offset},
        "geometry": {"type": "Point", "coordinates": [offset, offset]},
    }
    payload = json.dumps(
        {"type": "FeatureCollection", "features": [feature]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return FeatureBatch(
        sequence=sequence,
        first_feature_offset=offset,
        feature_count=1,
        payload=payload,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )


def make_pipeline(temporary_path, aggregate: Aggregate | None = None):
    runs = FakeRuns()
    validator = FakeValidator(aggregate)
    finalizer = FakeFinalizer()
    pipeline = StreamingVectorBufferPipeline(
        executor=FakeExecutor(),
        validator=validator,
        finalizer=finalizer,
        run_repository=runs,
    )
    transaction = StreamingFeatureCollectionTransaction(
        temporary_path,
        run_id="run:stream-pipeline",
        attempt=1,
        max_output_bytes=100_000,
        max_batches=10,
    )
    return pipeline, transaction, runs, validator


def test_pipeline_exhausts_batches_validates_and_finalizes(tmp_path):
    pipeline, transaction, runs, validator = make_pipeline(tmp_path)
    result = pipeline.execute(
        [make_batch(0, 0), make_batch(1, 1)],
        transaction=transaction,
        capability_version="1.0.0",
        input_crs={"authority": "EPSG:4326"},
        measurement_crs={"authority": "EPSG:3857"},
        parameters={"distance": 10},
        runtime_image_digest=_IMAGE,
        source_completion={"provider": "test", "dataset_id": "fixture"},
        artifact_id="artifact:streamed",
        artifact_version="1.0.0",
        output_port="result",
        created_by="test",
        output_crs={"authority": "EPSG:4326"},
    )

    assert result.batch_count == 2
    assert result.feature_count == 2
    assert result.duration_ms == 14
    assert transaction.state == "validated"
    assert runs.reports[0]["overall_status"] == "passed"
    assert validator.added == [(0, 0), (1, 1)]


def test_pipeline_does_not_publish_when_source_fails_before_eof(tmp_path):
    pipeline, transaction, runs, _ = make_pipeline(tmp_path)

    def broken_source():
        yield make_batch()
        raise OSError("source checksum mismatch")

    with pytest.raises(OSError, match="checksum mismatch"):
        pipeline.execute(
            broken_source(),
            transaction=transaction,
            capability_version="1.0.0",
            input_crs={"authority": "EPSG:4326"},
            measurement_crs={"authority": "EPSG:3857"},
            parameters={"distance": 10},
            runtime_image_digest=_IMAGE,
            source_completion={"provider": "test", "dataset_id": "fixture"},
            artifact_id="artifact:must-not-exist",
            artifact_version="1.0.0",
            output_port="result",
            created_by="test",
            output_crs={"authority": "EPSG:4326"},
        )

    assert transaction.state == "aborted"
    assert runs.run["status"] == "failed"
    assert runs.transitions[0]["event_type"] == "streaming_execution_failed"
