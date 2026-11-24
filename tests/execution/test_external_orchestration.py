from __future__ import annotations

import json
import os
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

    with pytest.raises(PermissionError) as raised:
        orchestrator.execute(
            run_id=run["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="artifact:never-created",
            artifact_version="1.0.0",
        )

    assert "must-not-be-persisted" not in str(raised.value)
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


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_external_source_run_executes_worker_validates_and_publishes(tmp_path):
    from tessellatum_foundry.execution.docker_worker import DockerWorker
    from tessellatum_foundry.sources.local import LocalFileSourceAdapter
    from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore

    source_path = tmp_path / "roads.geojson"
    source_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "road-node-1",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [320000, 9820000],
                        },
                        "properties": {"class": "primary"},
                    }
                ],
            },
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    cell = external_cell(source_path.as_uri())
    capability = fixture("capability.valid.json")
    runs = RunRepository(tmp_path / "control")
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    queued = ExternalVectorBufferRunFactory(run_repository=runs).create_queued_run(
        cell=cell, capability=capability
    )
    adapter = LocalFileSourceAdapter()
    worker = DockerWorker(timeout_seconds=90)
    orchestrator = ExternalVectorBufferRunOrchestrator(
        artifact_store=store,
        run_repository=runs,
        worker=worker,
        source_adapter_resolver=lambda reference: adapter,
        source_authorizer=lambda reference, actor_id: None,
        transaction_root=tmp_path / "transactions",
        max_batch_features=1,
        max_batch_bytes=1024 * 1024,
    )

    result = orchestrator.execute(
        run_id=queued["run_id"],
        cell=cell,
        capability=capability,
        actor_id="test-operator",
        artifact_id="derived.roads-buffer",
        artifact_version="1.0.0",
    )

    persisted_run = runs.get_run(queued["run_id"])
    assert persisted_run["status"] == "succeeded"
    assert persisted_run["source_references"] == queued["source_references"]
    assert persisted_run["input_snapshots"] == []
    assert persisted_run["cache"]["status"] == "bypassed"
    assert persisted_run["runtime_image_digest"].startswith("sha256:")
    assert result.batch_count == 1
    assert result.feature_count == 1
    assert result.validation_report["overall_status"] == "passed"
    assert result.validation_report["stage"] == "execution_output"

    artifact = store.get_artifact("derived.roads-buffer", "1.0.0")
    store.verify_artifact(artifact)
    output = json.loads(store.read_bytes(artifact))
    assert output["type"] == "FeatureCollection"
    assert len(output["features"]) == 1
    assert output["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert artifact["metadata"]["producer_run_id"] == queued["run_id"]
    assert artifact["metadata"]["producer_run_attempt"] == 1
    assert artifact["spatial"]["crs"] == {
        "authority": "EPSG",
        "code": 32737,
    }
    report = runs.get_validation_report(result.validation_report["report_id"])
    assert report["overall_status"] == "passed"
    assert report["subject"] == {"kind": "run", "id": queued["run_id"]}
