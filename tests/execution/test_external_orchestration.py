from __future__ import annotations

import json
from pathlib import Path

import pytest

from tessellatum_foundry.execution.external_orchestration import (
    ExternalVectorBufferRunOrchestrator,
)
from tessellatum_foundry.execution.external_runs import ExternalVectorBufferRunFactory
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.storage.artifacts import utc_timestamp


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"
MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def external_cell(uri: str = "file:///data/roads.geojson"):
    cell = fixture("cell.valid.json")
    cell["inputs"]["features"] = {
        "source": "external",
        "reference": {
            "provider": "local-file",
            "dataset_id": "roads-2026",
            "uri": uri,
            "media_type": MEDIA_TYPE,
            "version": "2026-11-23",
        },
        "spatial": {
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 32737},
            "geometry_types": ["Point"],
        },
    }
    return cell


class NeverWorker:
    pass


def test_authorization_is_checked_before_source_resolution_and_worker(tmp_path):
    runs = RunRepository(tmp_path / "control")
    cell = external_cell()
    capability = fixture("capability.valid.json")
    run = ExternalVectorBufferRunFactory(run_repository=runs).create_queued_run(
        cell=cell, capability=capability
    )
    resolver_calls = []

    def authorize(reference, actor_id):
        assert reference.dataset_id == "roads-2026"
        assert actor_id == "user:test"
        raise PermissionError("provider token=must-not-be-persisted")

    orchestrator = ExternalVectorBufferRunOrchestrator(
        artifact_store=None,
        run_repository=runs,
        worker=NeverWorker(),
        source_adapter_resolver=lambda reference: resolver_calls.append(reference),
        source_authorizer=authorize,
        transaction_root=tmp_path / "staging",
    )

    with pytest.raises(PermissionError):
        orchestrator.execute(
            run_id=run["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="artifact:never-created",
            artifact_version="1.0.0",
        )

    failed = runs.get_run(run["run_id"])
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "external_run.preflight_failed"
    assert "must-not-be-persisted" not in json.dumps(failed)
    assert resolver_calls == []
    assert not (tmp_path / "staging").exists()


def test_external_orchestrator_rejects_nonqueued_run_without_claiming_it(tmp_path):
    runs = RunRepository(tmp_path / "control")
    cell = external_cell()
    capability = fixture("capability.valid.json")
    run = ExternalVectorBufferRunFactory(run_repository=runs).create_queued_run(
        cell=cell, capability=capability
    )
    runs.transition(
        run["run_id"],
        expected_status="queued",
        new_status="failed",
        fields={
            "finished_at": utc_timestamp(),
            "error": {"code": "test.failed", "message": "Already failed.", "retryable": False},
        },
        event_type="test_failed",
    )
    orchestrator = ExternalVectorBufferRunOrchestrator(
        artifact_store=None,
        run_repository=runs,
        worker=NeverWorker(),
        source_adapter_resolver=lambda reference: None,
        source_authorizer=lambda reference, actor_id: None,
        transaction_root=tmp_path / "staging",
    )

    with pytest.raises(Exception, match="Only a queued Run"):
        orchestrator.execute(
            run_id=run["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="artifact:never-created",
            artifact_version="1.0.0",
        )

    assert runs.get_run(run["run_id"])["status"] == "failed"
    assert not (tmp_path / "staging").exists()
