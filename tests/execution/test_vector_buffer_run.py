from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tessellatum_foundry.execution.docker_worker import (
    DockerWorker,
    WorkerUnavailableError,
)
from tessellatum_foundry.execution.protocol import VectorBufferWorker, WorkerResult
from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.execution.service import VectorBufferRunService
from tessellatum_foundry.storage.artifacts import (
    FileSystemArtifactStore,
    ImmutableArtifactError,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"
MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"
PROJECTED = {"authority": "EPSG", "code": 32737}


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_input(store: FileSystemArtifactStore, *, invalid: bool = False) -> dict[str, Any]:
    if invalid:
        geometry = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
        }
        geometry_type = "Polygon"
    else:
        geometry = {"type": "Point", "coordinates": [320000, 9820000]}
        geometry_type = "Point"
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "source-1",
                "geometry": geometry,
                "properties": {"category": "test"},
            }
        ],
    }
    return store.put_bytes(
        artifact_id="source.points",
        version="1.0.0",
        content=json.dumps(feature_collection, allow_nan=False).encode("utf-8"),
        created_by="test-operator",
        media_type=MEDIA_TYPE,
        format_name="Foundry Spatial Feature Collection JSON",
        spatial={
            "kind": "vector",
            "crs": PROJECTED,
            "geometry_types": [geometry_type],
        },
    )


def bind_cell_to_input(input_artifact: dict[str, Any]) -> dict[str, Any]:
    cell = load_fixture("cell.valid.json")
    cell["inputs"]["features"]["artifact"] = {
        "artifact_id": input_artifact["artifact_id"],
        "version": input_artifact["version"],
    }
    return cell


def make_service(tmp_path: Path, worker: VectorBufferWorker):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    runs = RunRepository(tmp_path / "control")
    service = VectorBufferRunService(
        artifact_store=store,
        run_repository=runs,
        worker=worker,
    )
    return store, runs, service


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_vector_buffer_runs_in_isolated_docker_and_registers_artifact(tmp_path):
    worker = DockerWorker(timeout_seconds=90)
    store, runs, service = make_service(tmp_path, worker)
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    result = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert result.run["status"] == "succeeded", result.run.get("error")
    assert result.run["worker"]["worker_type"] == "local_docker"
    assert result.run["implementation"]["implementation_id"] == "vector-buffer-shapely"
    assert result.run["capability"] == {
        "capability_id": "vector.buffer",
        "version": "1.0.0",
    }
    assert result.run["runtime_image_digest"].startswith("sha256:")
    assert result.run["input_snapshots"][0]["artifact"] == {
        "artifact_id": input_artifact["artifact_id"],
        "version": input_artifact["version"],
    }
    assert result.output_artifact is not None
    assert result.validation_report is not None
    assert result.validation_report["overall_status"] == "passed"
    assert runs.get_run(result.run["run_id"])["status"] == "succeeded"

    output_bytes = store.read_bytes(result.output_artifact)
    output = json.loads(output_bytes)
    assert output["type"] == "FeatureCollection"
    assert output["features"][0]["geometry"]["type"] == "Polygon"
    assert result.output_artifact["spatial"]["crs"] == PROJECTED
    assert "rights" not in result.output_artifact

    with pytest.raises(RunStateError, match="immutable"):
        runs.transition(
            result.run["run_id"],
            expected_status="succeeded",
            new_status="failed",
            fields={"finished_at": result.run["finished_at"]},
            event_type="forbidden_mutation",
        )

    with pytest.raises(ImmutableArtifactError):
        store.put_bytes(
            artifact_id=result.output_artifact["artifact_id"],
            version=result.output_artifact["version"],
            content=b'{"type":"FeatureCollection","features":[]}',
            created_by="test-operator",
            media_type=MEDIA_TYPE,
            format_name="Foundry Spatial Feature Collection JSON",
            spatial=result.output_artifact["spatial"],
        )


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_failed_attempt_is_preserved_when_a_retry_succeeds(tmp_path):
    class MissingImageWorker(DockerWorker):
        def image_digest(self) -> str:
            raise WorkerUnavailableError("simulated transient image registry failure")

    store, runs, failed_service = make_service(tmp_path, MissingImageWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    first = failed_service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )
    assert first.run["status"] == "failed"
    assert first.run["attempt"] == 1

    retry_service = VectorBufferRunService(
        artifact_store=store,
        run_repository=runs,
        worker=DockerWorker(timeout_seconds=90),
    )
    second = retry_service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
        retry_of_run_id=first.run["run_id"],
    )

    assert second.run["status"] == "succeeded", second.run.get("error")
    assert second.run["attempt"] == 2
    assert second.run["retry_of_run_id"] == first.run["run_id"]
    assert runs.get_run(first.run["run_id"]) == first.run


class WrongCrsWorker:
    capability_id = "vector.buffer"
    capability_version = "1.0.0"
    implementation_id = "test-wrong-crs-worker"
    implementation_version = "1.0.0"
    worker_id = "test-worker"
    worker_type = "local_docker"

    def image_digest(self) -> str:
        return "sha256:" + "a" * 64

    def execute(self, **kwargs) -> WorkerResult:
        return WorkerResult(
            feature_collection={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "source-1",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [0, 0], [2, 0], [2, 2], [0, 2], [0, 0]
                            ]],
                        },
                        "properties": {"category": "test"},
                    }
                ],
            },
            crs={"authority": "EPSG", "code": 4326},
            geometry_types=("Polygon",),
            duration_ms=3,
            runtime_image_digest="sha256:" + "a" * 64,
        )


def test_output_critic_fails_run_without_registering_invalid_output(tmp_path):
    store, runs, service = make_service(tmp_path, WrongCrsWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    result = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert result.run["status"] == "failed"
    assert result.output_artifact is None
    assert result.validation_report is not None
    assert result.validation_report["overall_status"] == "failed"
    assert result.validation_report["report_id"] in result.run["validation_report_ids"]
    assert result.run["error"]["code"] == "output.validation_failed"
