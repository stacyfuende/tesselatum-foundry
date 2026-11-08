from __future__ import annotations

from copy import deepcopy
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
from tessellatum_foundry.execution.service import (
    ExecutionPreconditionError,
    VectorBufferRunService,
)
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


def make_input(
    store: FileSystemArtifactStore,
    *,
    invalid: bool = False,
    declared_geometry_types: list[str] | None = None,
) -> dict[str, Any]:
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
            "geometry_types": declared_geometry_types or [geometry_type],
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
    expected_manifest_checksum = service.implementations.manifest_checksum(
        "vector-buffer-shapely", "1.0.0"
    )
    assert result.run["implementation"]["manifest_checksum"] == expected_manifest_checksum
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
    assert result.validation_report["validator"] == {
        "name": "foundry-spatial-output-critic",
        "version": "0.2.0",
    }
    assert runs.get_run(result.run["run_id"])["status"] == "succeeded"

    output_bytes = store.read_bytes(result.output_artifact)
    output = json.loads(output_bytes)
    assert output["type"] == "FeatureCollection"
    assert output["features"][0]["geometry"]["type"] == "Polygon"
    assert result.output_artifact["spatial"]["crs"] == PROJECTED
    assert "rights" not in result.output_artifact
    assert result.output_artifact["metadata"]["rights_provenance"] == {
        "source_artifact": {
            "artifact_id": input_artifact["artifact_id"],
            "version": input_artifact["version"],
        },
        "declaration_status": "unknown",
    }
    assert len(result.run["validation_report_ids"]) == 2
    rights_report = runs.get_validation_report(
        f"report:{result.run['run_id']}:rights"
    )
    assert rights_report["stage"] == "rights_security"
    assert rights_report["overall_status"] == "requires_review"
    assert any(
        finding["code"] == "rights.permission_not_evaluated"
        and finding["status"] == "not_assessed"
        for finding in rights_report["findings"]
    )

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
    implementation_id = "vector-buffer-shapely"
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
    with pytest.raises(ExecutionPreconditionError, match="not marked as retryable"):
        service.execute(
            cell=cell,
            capability=capability,
            actor_id="test-operator",
            retry_of_run_id=result.run["run_id"],
        )


def test_run_service_rejects_worker_for_a_different_capability_version(tmp_path):
    class IncompatibleWorker(WrongCrsWorker):
        capability_version = "2.0.0"

    store, runs, service = make_service(tmp_path, IncompatibleWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    with pytest.raises(ExecutionPreconditionError, match="exact supplied Capability"):
        service.execute(
            cell=cell,
            capability=capability,
            actor_id="test-operator",
        )

    assert not (runs.root / "runs").exists()


def test_invalid_worker_runtime_digest_fails_the_run_cleanly(tmp_path):
    class InvalidDigestWorker(WrongCrsWorker):
        def image_digest(self) -> str:
            return "not-an-image-id"

    store, runs, service = make_service(tmp_path, InvalidDigestWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    result = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert result.run["status"] == "failed"
    assert result.run["error"]["code"] == "worker.unavailable"
    assert result.run["error"]["retryable"] is True
    assert result.output_artifact is None
    assert runs.get_run(result.run["run_id"])["status"] == "failed"



def test_run_preflight_rejects_geometry_type_metadata_mismatch(tmp_path):
    worker = WrongCrsWorker()
    store, runs, service = make_service(tmp_path, worker)
    input_artifact = make_input(store, declared_geometry_types=["Polygon"])
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    with pytest.raises(ExecutionPreconditionError, match="geometry_types metadata"):
        service.execute(
            cell=cell,
            capability=capability,
            actor_id="test-operator",
        )

    assert not (runs.root / "runs").exists()


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_worker_output_size_limit_prevents_artifact_registration(tmp_path):
    worker = DockerWorker(timeout_seconds=90, max_output_bytes=128)
    store, runs, service = make_service(tmp_path, worker)
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    result = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert result.run["status"] == "failed"
    assert result.run["error"]["code"] == "worker.execution_failed"
    assert "file-size limit" in result.run["error"]["message"]
    assert result.output_artifact is None
    assert result.run.get("outputs", []) == []


def test_run_service_rejects_unregistered_worker_implementation(tmp_path):
    class UnregisteredWorker(WrongCrsWorker):
        implementation_id = "unregistered-buffer-engine"

    store, runs, service = make_service(tmp_path, UnregisteredWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    with pytest.raises(ExecutionPreconditionError, match="not registered"):
        service.execute(
            cell=cell,
            capability=capability,
            actor_id="test-operator",
        )

    assert not (runs.root / "runs").exists()


def test_run_service_rejects_modified_capability_semantics_before_run(tmp_path):
    store, runs, service = make_service(tmp_path, WrongCrsWorker())
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")
    capability["parameter_schema"]["properties"]["distance"]["maximum"] = 1000

    with pytest.raises(ExecutionPreconditionError, match="differs from its canonical"):
        service.execute(
            cell=cell,
            capability=capability,
            actor_id="test-operator",
        )

    assert not (runs.root / "runs").exists()



class DeterministicBufferWorker(WrongCrsWorker):
    def __init__(self):
        self.calls = 0

    def execute(self, **kwargs) -> WorkerResult:
        self.calls += 1
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
                                [319900, 9819900],
                                [320100, 9819900],
                                [320100, 9820100],
                                [319900, 9820100],
                                [319900, 9819900],
                            ]],
                        },
                        "properties": {"category": "test"},
                    }
                ],
            },
            crs=PROJECTED,
            duration_ms=3,
            runtime_image_digest=kwargs["runtime_image_digest"],
        )


def test_deterministic_cache_reuses_only_validated_immutable_outputs(tmp_path):
    worker = DeterministicBufferWorker()
    store, runs, service = make_service(tmp_path, worker)
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

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
    assert second.run["cache"]["cache_key"] == first.run["cache"]["cache_key"]
    assert second.run["cache"]["source_run_id"] == first.run["run_id"]
    assert second.run["run_id"] != first.run["run_id"]
    assert second.run["outputs"] == first.run["outputs"]
    assert second.output_artifact == first.output_artifact
    assert second.validation_report["subject"] == {
        "kind": "run",
        "id": second.run["run_id"],
    }
    assert second.validation_report["validator"]["name"] == "foundry-cache-reuse"
    assert len(second.run["validation_report_ids"]) == 2
    rights_report = runs.get_validation_report(f"report:{second.run['run_id']}:rights")
    assert rights_report["overall_status"] == "requires_review"
    assert worker.calls == 1
    assert runs.get_run(second.run["run_id"])["cache"]["status"] == "hit"

    changed_cell = deepcopy(cell)
    changed_cell["parameters"]["distance"] += 1
    third = service.execute(
        cell=changed_cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert third.run["status"] == "succeeded"
    assert third.run["cache"]["status"] == "miss"
    assert third.run["cache"]["cache_key"] != first.run["cache"]["cache_key"]
    assert worker.calls == 2


@pytest.mark.parametrize(
    "corruption",
    [
        "validator_version",
        "validator_name",
        "failed_finding",
        "duplicate_finding",
        "missing_assessment",
        "missing_validator",
        "malformed_findings",
        "malformed_assessment",
    ],
)
def test_cache_rejects_stale_or_incomplete_output_validation_evidence(
    tmp_path, monkeypatch, corruption
):
    worker = DeterministicBufferWorker()
    store, runs, service = make_service(tmp_path, worker)
    input_artifact = make_input(store)
    cell = bind_cell_to_input(input_artifact)
    capability = load_fixture("capability.valid.json")

    first = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )
    assert first.run["status"] == "succeeded"

    original_get_report = runs.get_validation_report

    def corrupted_report(report_id):
        report = deepcopy(original_get_report(report_id))
        if corruption == "validator_version":
            report["validator"]["version"] = "0.0.0"
        elif corruption == "validator_name":
            report["validator"]["name"] = "legacy-output-critic"
        elif corruption == "failed_finding":
            report["findings"][0]["status"] = "failed"
        elif corruption == "duplicate_finding":
            report["findings"].append(deepcopy(report["findings"][0]))
        elif corruption == "missing_assessment":
            report["assessed_dimensions"].remove("feature_metadata")
        elif corruption == "missing_validator":
            report["validator"] = None
        elif corruption == "malformed_findings":
            report["findings"] = None
        else:
            report["assessed_dimensions"] = None
        return report

    monkeypatch.setattr(runs, "get_validation_report", corrupted_report)
    second = service.execute(
        cell=cell,
        capability=capability,
        actor_id="test-operator",
    )

    assert second.run["status"] == "succeeded"
    assert second.run["cache"]["status"] == "miss"
    assert worker.calls == 2
