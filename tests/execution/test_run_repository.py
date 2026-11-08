from __future__ import annotations

from pathlib import Path

import pytest

from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.storage.artifacts import utc_timestamp

_DIGEST = "a" * 64


def create_running_run(root: Path) -> tuple[RunRepository, dict]:
    repository = RunRepository(root)
    repository.create_queued_run(
        run_id="run:immutable-provenance",
        cell={"cell_id": "buffer-buildings", "version": "1.0.0"},
        capability={"capability_id": "vector.buffer", "version": "1.0.0"},
        input_snapshots=[
            {
                "input_port": "features",
                "artifact": {
                    "artifact_id": "dataset.buildings",
                    "version": "1.0.0",
                },
                "checksum": _DIGEST,
            }
        ],
        normalized_parameters={"distance": 100, "unit": "metre"},
    )
    running = repository.transition(
        "run:immutable-provenance",
        expected_status="queued",
        new_status="running",
        fields={
            "started_at": utc_timestamp(),
            "worker": {
                "worker_id": "local-test-worker",
                "worker_type": "local_docker",
            },
            "implementation": {
                "implementation_id": "vector-buffer-shapely",
                "version": "1.0.0",
                "manifest_checksum": _DIGEST,
            },
            "runtime_image_digest": "sha256:" + _DIGEST,
        },
        event_type="worker_started",
    )
    return repository, running


def test_run_transition_cannot_rewrite_immutable_input_provenance(tmp_path):
    repository, running = create_running_run(tmp_path)

    with pytest.raises(RunStateError, match="input_snapshots.*immutable"):
        repository.transition(
            running["run_id"],
            expected_status="running",
            new_status="failed",
            fields={
                "input_snapshots": [],
                "finished_at": utc_timestamp(),
                "error": {"code": "test.failure", "message": "test"},
            },
            event_type="run_failed",
        )

    assert repository.get_run(running["run_id"]) == running


def test_run_transition_cannot_replace_worker_or_implementation_identity(tmp_path):
    repository, running = create_running_run(tmp_path)

    with pytest.raises(RunStateError, match="implementation.*cannot be changed"):
        repository.transition(
            running["run_id"],
            expected_status="running",
            new_status="failed",
            fields={
                "implementation": {
                    "implementation_id": "different-engine",
                    "version": "1.0.0",
                    "manifest_checksum": _DIGEST,
                },
                "finished_at": utc_timestamp(),
                "error": {"code": "test.failure", "message": "test"},
            },
            event_type="run_failed",
        )

    assert repository.get_run(running["run_id"]) == running


def test_run_can_still_transition_to_terminal_state_without_rewriting_provenance(tmp_path):
    repository, running = create_running_run(tmp_path)

    failed = repository.transition(
        running["run_id"],
        expected_status="running",
        new_status="failed",
        fields={
            "finished_at": utc_timestamp(),
            "error": {"code": "test.failure", "message": "test"},
        },
        event_type="run_failed",
    )

    assert failed["status"] == "failed"
    assert failed["cell"] == running["cell"]
    assert failed["input_snapshots"] == running["input_snapshots"]
    assert failed["implementation"] == running["implementation"]


def test_run_transition_rejects_fields_not_valid_for_target_state(tmp_path):
    repository, running = create_running_run(tmp_path)

    with pytest.raises(RunStateError, match="outputs are not permitted"):
        repository.transition(
            running["run_id"],
            expected_status="running",
            new_status="failed",
            fields={
                "outputs": [],
                "finished_at": utc_timestamp(),
                "error": {"code": "test.failure", "message": "test"},
            },
            event_type="run_failed",
        )

    assert repository.get_run(running["run_id"]) == running
