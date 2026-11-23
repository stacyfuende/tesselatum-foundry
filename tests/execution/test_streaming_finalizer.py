from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pytest

from tessellatum_foundry.execution import (
    RunRepository,
    StreamingRunFinalizer,
)
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore, utc_timestamp
from tessellatum_foundry.storage.streaming import StreamingFeatureCollectionTransaction


_DIGEST = "a" * 64


@dataclass
class Batch:
    sequence: int
    first_feature_offset: int
    feature_count: int
    payload: bytes
    output_checksum_sha256: str


def _setup(tmp_path):
    runs = RunRepository(tmp_path / "runs")
    queued = runs.create_queued_run(
        run_id="run:stream-finalize",
        cell={"cell_id": "buffer-buildings", "version": "1.0.0"},
        capability={"capability_id": "vector.buffer", "version": "1.0.0"},
        input_snapshots=[{
            "input_port": "features",
            "artifact": {"artifact_id": "input.buildings", "version": "1.0.0"},
            "checksum": _DIGEST,
        }],
        normalized_parameters={"distance": 10, "unit": "metre"},
    )
    runs.transition(
        queued["run_id"],
        expected_status="queued",
        new_status="running",
        fields={
            "started_at": utc_timestamp(),
            "worker": {"worker_id": "worker:test", "worker_type": "local_docker"},
            "implementation": {
                "implementation_id": "vector-buffer-test",
                "version": "1.0.0",
                "manifest_checksum": _DIGEST,
            },
            "runtime_image_digest": "sha256:" + _DIGEST,
        },
        event_type="worker_started",
    )
    report = {
        "report_id": "report:stream-finalize",
        "subject": {"kind": "run", "id": queued["run_id"]},
        "stage": "execution_output",
        "overall_status": "passed",
        "created_at": utc_timestamp(),
        "validator": {"name": "test-output-critic", "version": "1.0.0"},
        "findings": [],
    }
    runs.save_validation_report(report)

    feature_payload = json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"id": 1}, "geometry": None}],
    }, sort_keys=True, separators=(",", ":")).encode()
    batch = Batch(0, 0, 1, feature_payload, hashlib.sha256(feature_payload).hexdigest())
    transaction = StreamingFeatureCollectionTransaction(
        tmp_path / "transactions",
        run_id=queued["run_id"],
        attempt=queued["attempt"],
        max_output_bytes=100_000,
        max_batches=5,
    )
    transaction.append(batch)
    transaction.seal_input({"eof_verified": True})
    transaction.seal_output()
    transaction.mark_validated({"passed": True, "validator": "test-output-critic"})
    artifacts = FileSystemArtifactStore(tmp_path / "artifacts")
    finalizer = StreamingRunFinalizer(artifact_store=artifacts, run_repository=runs)
    return runs, artifacts, transaction, finalizer, report


def test_finalizer_publishes_artifact_then_marks_run_succeeded(tmp_path):
    runs, artifacts, transaction, finalizer, report = _setup(tmp_path)

    result = finalizer.finalize(
        transaction,
        artifact_id="artifact:stream-final",
        artifact_version="1.0.0",
        output_port="result",
        validation_report_id=report["report_id"],
        created_by="system:test",
    )

    assert result.run["status"] == "succeeded"
    assert result.artifact["metadata"]["producer_run_id"] == result.run["run_id"]
    assert result.artifact["metadata"]["producer_run_attempt"] == result.run["attempt"]
    assert transaction.state == "committed"
    assert runs.get_run(result.run["run_id"]) == result.run
    artifacts.verify_artifact(result.artifact)


def test_finalizer_recovers_artifact_commit_and_completes_run_after_interruption(tmp_path):
    runs, artifacts, transaction, finalizer, report = _setup(tmp_path)
    original_persist = transaction._persist
    calls = 0

    def interrupt_after_artifact_commit():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated crash after Artifact metadata commit")
        original_persist()

    transaction._persist = interrupt_after_artifact_commit
    with pytest.raises(OSError, match="simulated crash"):
        finalizer.finalize(
            transaction,
            artifact_id="artifact:stream-crash",
            artifact_version="1.0.0",
            output_port="result",
            validation_report_id=report["report_id"],
            created_by="system:test",
        )

    assert runs.get_run(transaction.run_id)["status"] == "running"

    recovered = finalizer.recover_and_finalize(
        tmp_path / "transactions",
        transaction.transaction_id,
        output_port="result",
        validation_report_id=report["report_id"],
    )

    assert recovered.run["status"] == "succeeded"
    assert recovered.artifact["artifact_id"] == "artifact:stream-crash"
    assert runs.get_run(transaction.run_id)["status"] == "succeeded"
