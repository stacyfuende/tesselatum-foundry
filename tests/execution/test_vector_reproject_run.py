from __future__ import annotations

import json
import os
from copy import deepcopy
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
        self.calls = 0

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
        self.calls += 1
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
    assert result.run["cache"]["status"] == "miss"
    assert result.validation_report["validator"] == {
        "name": "foundry-spatial-output-critic",
        "version": "0.2.0",
    }
    assert result.output_artifact is not None
    assert result.output_artifact["spatial"]["crs"] == TARGET_CRS
    assert result.output_artifact["spatial"]["geometry_types"] == ["Point"]
    assert result.validation_report["overall_status"] == "passed"
    assert result.validation_report["validator"] == {
        "name": "foundry-spatial-output-critic",
        "version": "0.2.0",
    }
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


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_recipe_dispatches_reproject_then_buffer_across_two_capability_runners(tmp_path):
    from tessellatum_foundry.execution.docker_worker import DockerWorker
    from tessellatum_foundry.execution.recipes import RecipeExecutionService
    from tessellatum_foundry.execution.service import VectorBufferRunService

    store = FileSystemArtifactStore(tmp_path / "artifacts")
    runs = RunRepository(tmp_path / "control")
    input_artifact = make_input(store)
    reproject_cell = make_cell(input_artifact)
    buffer_cell = {
        "cell_id": "buffer-projected-sites",
        "version": "1.0.0",
        "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
        "inputs": {
            "features": {
                "source": "cell_output",
                "cell_id": reproject_cell["cell_id"],
                "cell_version": reproject_cell["version"],
                "output_port": "result",
            }
        },
        "parameters": {"distance": 10, "unit": "metre"},
        "output_contracts": {
            "result": {
                "data_kind": "vector",
                "media_types": [MEDIA_TYPE],
                "crs": TARGET_CRS,
                "geometry_types": ["Polygon", "MultiPolygon"],
            }
        },
        "constraints": {
            "measurement_crs": TARGET_CRS,
            "linear_unit": "metre",
            "required_geometry_validity": True,
        },
    }
    recipe = {
        "recipe_id": "reproject-and-buffer-sites",
        "version": "1.0.0",
        "title": "Reproject and buffer sites",
        "nodes": [
            {
                "node_id": "reproject",
                "cell": {
                    "cell_id": reproject_cell["cell_id"],
                    "version": reproject_cell["version"],
                },
            },
            {
                "node_id": "buffer",
                "cell": {
                    "cell_id": buffer_cell["cell_id"],
                    "version": buffer_cell["version"],
                },
            },
        ],
        "edges": [
            {
                "from": {"node_id": "reproject", "output_port": "result"},
                "to": {"node_id": "buffer", "input_port": "features"},
            }
        ],
        "declared_outputs": [
            {"name": "buffered_sites", "node_id": "buffer", "output_port": "result"}
        ],
    }
    reproject_service = VectorReprojectRunService(
        artifact_store=store,
        run_repository=runs,
        worker=DockerVectorReprojectWorker(timeout_seconds=90),
    )
    buffer_service = VectorBufferRunService(
        artifact_store=store,
        run_repository=runs,
        worker=DockerWorker(timeout_seconds=90),
    )
    recipe_service = RecipeExecutionService(
        artifact_store=store,
        cell_runners={
            ("vector.reproject", "1.0.0"): reproject_service,
            ("vector.buffer", "1.0.0"): buffer_service,
        },
    )
    capabilities = {
        ("vector.reproject", "1.0.0"): reproject_service.capabilities.get(
            "vector.reproject", "1.0.0"
        ),
        ("vector.buffer", "1.0.0"): buffer_service.capabilities.get(
            "vector.buffer", "1.0.0"
        ),
    }

    result = recipe_service.execute(
        recipe=recipe,
        cells={
            (reproject_cell["cell_id"], reproject_cell["version"]): reproject_cell,
            (buffer_cell["cell_id"], buffer_cell["version"]): buffer_cell,
        },
        capabilities=capabilities,
        actor_id="test-operator",
    )

    assert result.status == "succeeded", result.error
    assert result.node_results["reproject"].run["status"] == "succeeded"
    assert result.node_results["buffer"].run["status"] == "succeeded"
    buffer_run = result.node_results["buffer"].run
    assert buffer_run["input_snapshots"][0]["source_run_id"] == (
        result.node_results["reproject"].run["run_id"]
    )
    buffered = result.outputs["buffered_sites"]
    assert buffered["spatial"]["crs"] == TARGET_CRS
    assert buffered["spatial"]["geometry_types"] == ["Polygon"]


def test_reproject_run_executes_through_authenticated_remote_worker(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer

    from tessellatum_foundry.execution.remote_worker import RemoteVectorReprojectWorker
    from tessellatum_foundry.worker.http_server import WorkerHandler

    digest = "sha256:" + "e" * 64
    monkeypatch.setenv("FOUNDRY_REMOTE_WORKER_TOKEN", "test-secret")
    monkeypatch.setenv("FOUNDRY_WORKER_IMAGE_DIGEST", digest)
    monkeypatch.setenv("FOUNDRY_WORKER_CAPABILITY_ID", "vector.reproject")
    monkeypatch.setenv("FOUNDRY_WORKER_CAPABILITY_VERSION", "1.0.0")
    monkeypatch.setenv(
        "FOUNDRY_IMPLEMENTATION_ID", "vector-reproject-pyproj-shapely"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        worker = RemoteVectorReprojectWorker(
            f"http://127.0.0.1:{server.server_port}",
            bearer_token="test-secret",
            allow_insecure_localhost=True,
        )
        store, _, service = make_service(tmp_path, worker)
        artifact = make_input(store)
        result = service.execute(
            cell=make_cell(artifact),
            capability=service.capabilities.get("vector.reproject", "1.0.0"),
            actor_id="test-operator",
        )
        assert result.run["status"] == "succeeded", result.run.get("error")
        assert result.run["worker"]["worker_type"] == "remote"
        assert result.run["runtime_image_digest"] == digest
        assert result.validation_report["overall_status"] == "passed"
        assert result.output_artifact["spatial"]["crs"] == TARGET_CRS
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_reproject_cache_reuses_only_output_critic_validated_artifacts(tmp_path):
    worker = FakeReprojectWorker()
    store, runs, service = make_service(tmp_path, worker)
    artifact = make_input(store)
    cell = make_cell(artifact)
    capability = service.capabilities.get("vector.reproject", "1.0.0")

    first = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )
    second = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert first.run["status"] == "succeeded"
    assert first.run["cache"]["status"] == "miss"
    assert second.run["status"] == "succeeded"
    assert second.run["cache"]["status"] == "hit"
    assert second.run["cache"]["source_run_id"] == first.run["run_id"]
    assert second.run["outputs"] == first.run["outputs"]
    assert second.output_artifact == first.output_artifact
    assert second.validation_report["validator"]["name"] == "foundry-cache-reuse"
    assert worker.calls == 1
    assert runs.get_run(second.run["run_id"])["cache"]["status"] == "hit"


def test_reproject_cache_rejects_failed_target_crs_validation_evidence(
    tmp_path, monkeypatch
):
    worker = FakeReprojectWorker()
    store, runs, service = make_service(tmp_path, worker)
    artifact = make_input(store)
    cell = make_cell(artifact)
    capability = service.capabilities.get("vector.reproject", "1.0.0")
    first = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )
    assert first.run["status"] == "succeeded"

    original_get_report = runs.get_validation_report

    def corrupt_target_crs(report_id):
        report = deepcopy(original_get_report(report_id))
        for finding in report["findings"]:
            if finding["code"] == "output.crs_matches_contract":
                finding["status"] = "failed"
        return report

    monkeypatch.setattr(runs, "get_validation_report", corrupt_target_crs)
    second = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert second.run["status"] == "succeeded"
    assert second.run["cache"]["status"] == "miss"
    assert worker.calls == 2


def test_reproject_cache_rejects_buffer_crs_finding_as_target_evidence(
    tmp_path, monkeypatch
):
    worker = FakeReprojectWorker()
    store, runs, service = make_service(tmp_path, worker)
    artifact = make_input(store)
    cell = make_cell(artifact)
    capability = service.capabilities.get("vector.reproject", "1.0.0")
    first = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )
    assert first.run["status"] == "succeeded"

    original_get_report = runs.get_validation_report

    def replace_target_crs_with_input_crs(report_id):
        report = deepcopy(original_get_report(report_id))
        for finding in report["findings"]:
            if finding["code"] == "output.crs_matches_contract":
                finding["code"] = "output.crs_matches_input"
        return report

    monkeypatch.setattr(runs, "get_validation_report", replace_target_crs_with_input_crs)
    second = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert second.run["status"] == "succeeded"
    assert second.run["cache"]["status"] == "miss"
    assert worker.calls == 2
