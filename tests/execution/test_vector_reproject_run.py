from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tessellatum_foundry.capabilities.vector_reproject import reproject_feature_collection
from tessellatum_foundry.execution.docker_worker import DockerVectorReprojectWorker
from tessellatum_foundry.execution.protocol import WorkerResult
from tessellatum_foundry.execution.reproject_service import VectorReprojectRunService
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import ExecutionPreconditionError
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore


MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"
SOURCE_CRS = {"authority": "EPSG", "code": 4326}
TARGET_CRS = {"authority": "EPSG", "code": 32737}


def make_input(store: FileSystemArtifactStore) -> dict[str, Any]:
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "site-01",
            "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
            "properties": {"name": "Nairobi"},
        }],
    }
    return store.put_bytes(
        artifact_id="source.sites",
        version="1.0.0",
        content=json.dumps(collection, allow_nan=False).encode("utf-8"),
        created_by="test-operator",
        media_type=MEDIA_TYPE,
        format_name="Foundry Spatial Feature Collection JSON",
        spatial={
            "kind": "vector",
            "crs": SOURCE_CRS,
            "geometry_types": ["Point"],
        },
    )


def make_cell(input_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_id": "sites-to-utm",
        "version": "1.0.0",
        "capability": {"capability_id": "vector.reproject", "version": "1.0.0"},
        "inputs": {
            "features": {
                "source": "artifact",
                "artifact": {
                    "artifact_id": input_artifact["artifact_id"],
                    "version": input_artifact["version"],
                },
            }
        },
        "parameters": {"target_crs": TARGET_CRS},
        "output_contracts": {
            "result": {
                "data_kind": "vector",
                "media_types": [MEDIA_TYPE],
                "crs": TARGET_CRS,
                "geometry_types": ["Point"],
            }
        },
    }


class FakeReprojectWorker:
    capability_id = "vector.reproject"
    capability_version = "1.0.0"
    implementation_id = "vector-reproject-pyproj-shapely"
    implementation_version = "1.0.0"
    worker_id = "test-reproject-worker"
    worker_type = "local_docker"

    def __init__(self, *, wrong_crs: bool = False, mutate_properties: bool = False):
        self.wrong_crs = wrong_crs
        self.mutate_properties = mutate_properties

    def image_digest(self) -> str:
        return "sha256:" + "a" * 64

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict[str, Any],
        target_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        collection = json.loads(input_bytes)
        result = reproject_feature_collection(
            collection,
            input_crs=input_crs,
            target_crs=target_crs,
        )
        output = result.feature_collection
        if self.mutate_properties:
            output["features"][0]["properties"]["name"] = "tampered"
        return WorkerResult(
            feature_collection=output,
            crs=(
                {"authority": "EPSG", "code": 3857}
                if self.wrong_crs
                else target_crs
            ),
            duration_ms=4,
            runtime_image_digest=runtime_image_digest or self.image_digest(),
        )


def make_service(tmp_path: Path, worker):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    runs = RunRepository(tmp_path / "control")
    service = VectorReprojectRunService(
        artifact_store=store,
        run_repository=runs,
        worker=worker,
    )
    return store, runs, service


def test_reproject_run_persists_output_artifact_and_validation_evidence(tmp_path):
    store, runs, service = make_service(tmp_path, FakeReprojectWorker())
    artifact = make_input(store)
    cell = make_cell(artifact)
    capability = service.capabilities.get("vector.reproject", "1.0.0")

    result = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert result.run["status"] == "succeeded", result.run.get("error")
    assert result.run["capability"] == {
        "capability_id": "vector.reproject",
        "version": "1.0.0",
    }
    assert result.run["implementation"]["implementation_id"] == (
        "vector-reproject-pyproj-shapely"
    )
    assert result.output_artifact is not None
    assert result.output_artifact["spatial"]["crs"] == TARGET_CRS
    assert result.output_artifact["spatial"]["geometry_types"] == ["Point"]
    assert result.validation_report["overall_status"] == "passed"
    output = json.loads(store.read_bytes(result.output_artifact))
    assert output["features"][0]["id"] == "site-01"
    assert output["features"][0]["properties"] == {"name": "Nairobi"}
    assert runs.get_run(result.run["run_id"])["status"] == "succeeded"


def test_reproject_run_fails_closed_when_worker_reports_wrong_crs(tmp_path):
    store, _, service = make_service(tmp_path, FakeReprojectWorker(wrong_crs=True))
    artifact = make_input(store)
    result = service.execute(
        cell=make_cell(artifact),
        capability=service.capabilities.get("vector.reproject", "1.0.0"),
        actor_id="test-operator",
    )
    assert result.run["status"] == "failed"
    assert result.run["error"]["code"] == "output.validation_failed"
    assert result.output_artifact is None
    assert result.validation_report["overall_status"] == "failed"


def test_reproject_run_fails_closed_when_worker_changes_feature_metadata(tmp_path):
    store, _, service = make_service(
        tmp_path, FakeReprojectWorker(mutate_properties=True)
    )
    artifact = make_input(store)
    result = service.execute(
        cell=make_cell(artifact),
        capability=service.capabilities.get("vector.reproject", "1.0.0"),
        actor_id="test-operator",
    )
    assert result.run["status"] == "failed"
    assert result.run["error"]["code"] == "output.validation_failed"
    assert result.output_artifact is None


def test_reproject_run_requires_output_contract_to_match_target_crs(tmp_path):
    store, runs, service = make_service(tmp_path, FakeReprojectWorker())
    artifact = make_input(store)
    cell = make_cell(artifact)
    cell["output_contracts"]["result"]["crs"] = {
        "authority": "EPSG",
        "code": 3857,
    }
    with pytest.raises(ExecutionPreconditionError, match="must equal"):
        service.execute(
            cell=cell,
            capability=service.capabilities.get("vector.reproject", "1.0.0"),
            actor_id="test-operator",
        )
    assert not (runs.root / "runs").exists()


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_vector_reproject_executes_in_isolated_docker_worker(tmp_path):
    store, runs, service = make_service(
        tmp_path, DockerVectorReprojectWorker(timeout_seconds=90)
    )
    artifact = make_input(store)
    result = service.execute(
        cell=make_cell(artifact),
        capability=service.capabilities.get("vector.reproject", "1.0.0"),
        actor_id="test-operator",
    )
    assert result.run["status"] == "succeeded", result.run.get("error")
    assert result.run["worker"]["worker_type"] == "local_docker"
    assert result.output_artifact["spatial"]["crs"] == TARGET_CRS
    assert result.validation_report["overall_status"] == "passed"
