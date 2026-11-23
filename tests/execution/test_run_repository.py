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


def test_run_listing_preserves_creation_order_when_timestamps_match(tmp_path, monkeypatch):
    import tessellatum_foundry.execution.runs as runs_module

    monkeypatch.setattr(runs_module, "utc_timestamp", lambda: "2026-11-08T17:00:00Z")
    repository = RunRepository(tmp_path)
    common = {
        "cell": {"cell_id": "buffer-buildings", "version": "1.0.0"},
        "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
        "input_snapshots": [
            {
                "input_port": "features",
                "artifact": {"artifact_id": "dataset.buildings", "version": "1.0.0"},
                "checksum": _DIGEST,
            }
        ],
        "normalized_parameters": {"distance": 100, "unit": "metre"},
    }

    first = repository.create_queued_run(run_id="run:first-created", **common)
    second = repository.create_queued_run(run_id="run:second-created", **common)

    listed = repository.list_runs()
    assert [record["run_id"] for record in listed] == [
        "run:first-created",
        "run:second-created",
    ]
    assert [record["creation_sequence"] for record in listed] == [1, 2]
    assert first["creation_sequence"] == 1
    assert second["creation_sequence"] == 2


def test_run_creation_sequence_continues_after_repository_reopen(tmp_path):
    first_repository = RunRepository(tmp_path)
    common = {
        "cell": {"cell_id": "buffer-buildings", "version": "1.0.0"},
        "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
        "input_snapshots": [
            {
                "input_port": "features",
                "artifact": {"artifact_id": "dataset.buildings", "version": "1.0.0"},
                "checksum": _DIGEST,
            }
        ],
        "normalized_parameters": {"distance": 100, "unit": "metre"},
    }
    first_repository.create_queued_run(run_id="run:before-reopen", **common)

    reopened = RunRepository(tmp_path)
    second = reopened.create_queued_run(run_id="run:after-reopen", **common)

    assert second["creation_sequence"] == 2


def test_external_source_evidence_is_persisted_and_immutable(tmp_path):
    repository = RunRepository(tmp_path)
    source_references = [
        {
            "input_port": "features",
            "reference": {
                "provider": "customer-catalog",
                "dataset_id": "roads-current",
                "uri": "https://data.example.test/roads",
                "version": "2026-11-22",
                "media_type": "application/geo+json",
            },
        }
    ]
    queued = repository.create_queued_run(
        run_id="run:external-source-evidence",
        cell={"cell_id": "buffer-buildings", "version": "1.0.0"},
        capability={"capability_id": "vector.buffer", "version": "1.0.0"},
        input_snapshots=[
            {
                "input_port": "features",
                "artifact": {"artifact_id": "dataset.buildings", "version": "1.0.0"},
                "checksum": _DIGEST,
            }
        ],
        normalized_parameters={"distance": 100, "unit": "metre"},
        source_references=source_references,
    )

    assert queued["source_references"] == source_references
    with pytest.raises(RunStateError, match="source_references.*immutable"):
        repository.transition(
            queued["run_id"],
            expected_status="queued",
            new_status="failed",
            fields={
                "source_references": [],
                "finished_at": utc_timestamp(),
                "error": {"code": "test.failure", "message": "test"},
            },
            event_type="run_failed",
        )
    assert repository.get_run(queued["run_id"]) == queued
