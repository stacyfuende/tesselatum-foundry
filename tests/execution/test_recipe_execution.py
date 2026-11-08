from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tessellatum_foundry.execution.docker_worker import DockerWorker
from tessellatum_foundry.execution.protocol import WorkerResult
from tessellatum_foundry.execution.recipes import (
    RecipeExecutionPreconditionError,
    RecipeExecutionService,
)
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import VectorBufferRunService
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"
MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"
CRS = {"authority": "EPSG", "code": 32737}
IMAGE_ID = "sha256:" + "c" * 64


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def create_source_artifact(store: FileSystemArtifactStore) -> dict[str, Any]:
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "source-point",
                "geometry": {"type": "Point", "coordinates": [320000, 9820000]},
                "properties": {"class": "test"},
            }
        ],
    }
    return store.put_bytes(
        artifact_id="source.points",
        version="1.0.0",
        content=json.dumps(feature_collection, allow_nan=False).encode("utf-8"),
        created_by="recipe-test",
        media_type=MEDIA_TYPE,
        format_name="Foundry Spatial Feature Collection JSON",
        spatial={"kind": "vector", "crs": CRS, "geometry_types": ["Point"]},
    )


def make_cell_chain(
    source_artifact: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    first = load_fixture("cell.valid.json")
    first["cell_id"] = "buffer-first"
    first["inputs"]["features"]["artifact"] = {
        "artifact_id": source_artifact["artifact_id"],
        "version": source_artifact["version"],
    }

    second = deepcopy(first)
    second["cell_id"] = "buffer-second"
    second["inputs"]["features"] = {
        "source": "cell_output",
        "cell_id": first["cell_id"],
        "cell_version": first["version"],
        "output_port": "result",
    }

    third = deepcopy(first)
    third["cell_id"] = "buffer-third"
    third["inputs"]["features"] = {
        "source": "cell_output",
        "cell_id": second["cell_id"],
        "cell_version": second["version"],
        "output_port": "result",
    }
    return first, second, third


def make_recipe(cells: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    nodes = [
        {
            "node_id": cell["cell_id"].replace("buffer-", ""),
            "cell": {"cell_id": cell["cell_id"], "version": cell["version"]},
        }
        for cell in cells
    ]
    edges = [
        {
            "from": {"node_id": "first", "output_port": "result"},
            "to": {"node_id": "second", "input_port": "features"},
        },
        {
            "from": {"node_id": "second", "output_port": "result"},
            "to": {"node_id": "third", "input_port": "features"},
        },
    ]
    return {
        "recipe_id": "three-buffer-steps",
        "version": "1.0.0",
        "title": "Three sequential buffers",
        "nodes": list(reversed(nodes)),
        "edges": edges,
        "declared_outputs": [
            {"name": "final", "node_id": "third", "output_port": "result"}
        ],
    }


def make_runner(
    tmp_path: Path,
    worker,
) -> tuple[FileSystemArtifactStore, RunRepository, RecipeExecutionService]:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    runs = RunRepository(tmp_path / "control")
    cell_runner = VectorBufferRunService(
        artifact_store=store,
        run_repository=runs,
        worker=worker,
    )
    recipes = RecipeExecutionService(cell_runner=cell_runner, artifact_store=store)
    return store, runs, recipes


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_single_node_recipe_executes_and_persists_recipe_correlation(tmp_path):
    worker = DockerWorker(timeout_seconds=90)
    store, runs, recipes = make_runner(tmp_path, worker)
    source = create_source_artifact(store)
    cell = load_fixture("cell.valid.json")
    cell["inputs"]["features"]["artifact"] = {
        "artifact_id": source["artifact_id"],
        "version": source["version"],
    }
    capability = load_fixture("capability.valid.json")
    recipe = load_fixture("recipe.valid.json")

    result = recipes.execute(
        recipe=recipe,
        cells={(cell["cell_id"], cell["version"]): cell},
        capabilities={(capability["capability_id"], capability["version"]): capability},
        actor_id="recipe-test",
    )

    assert result.status == "succeeded"
    assert result.failed_node_id is None
    assert set(result.outputs) == {"buffered_buildings"}
    assert len(result.node_results) == 1
    run = result.node_results["buffer"].run
    assert run["recipe"] == {
        "recipe_id": recipe["recipe_id"],
        "version": recipe["version"],
    }
    assert run["recipe_execution_id"] == result.execution_id
    assert runs.list_runs_for_recipe_execution(result.execution_id) == [run]


class SequenceWorker:
    capability_id = "vector.buffer"
    capability_version = "1.0.0"
    implementation_id = "vector-buffer-shapely"
    implementation_version = "1.0.0"
    worker_id = "test-sequence-worker"
    worker_type = "local_docker"

    def __init__(self) -> None:
        self.calls = 0

    def image_digest(self) -> str:
        return IMAGE_ID

    def execute(self, **kwargs: Any) -> WorkerResult:
        self.calls += 1
        source = json.loads(kwargs["input_bytes"])
        for feature in source["features"]:
            feature["geometry"] = {
                "type": "Polygon",
                "coordinates": [[
                    [319990, 9819990],
                    [320010, 9819990],
                    [320010, 9820010],
                    [319990, 9820010],
                    [319990, 9819990],
                ]],
            }
        output_crs = CRS if self.calls == 1 else {"authority": "EPSG", "code": 4326}
        return WorkerResult(
            feature_collection=source,
            crs=output_crs,
            duration_ms=5,
            runtime_image_digest=IMAGE_ID,
        )


def test_recipe_resolves_upstream_artifacts_and_stops_after_failed_node(tmp_path):
    worker = SequenceWorker()
    store, runs, recipes = make_runner(tmp_path, worker)
    source = create_source_artifact(store)
    cells = make_cell_chain(source)
    recipe = make_recipe(cells)
    capability = load_fixture("capability.valid.json")
    cell_map = {(cell["cell_id"], cell["version"]): cell for cell in cells}
    capability_map = {
        (capability["capability_id"], capability["version"]): capability
    }

    result = recipes.execute(
        recipe=recipe,
        cells=cell_map,
        capabilities=capability_map,
        actor_id="recipe-test",
    )

    assert result.status == "failed"
    assert result.failed_node_id == "second"
    assert worker.calls == 2
    assert set(result.node_results) == {"first", "second"}
    first_run = result.node_results["first"].run
    second_run = result.node_results["second"].run
    assert first_run["status"] == "succeeded"
    assert second_run["status"] == "failed"
    assert first_run["recipe_execution_id"] == result.execution_id
    assert second_run["recipe_execution_id"] == result.execution_id
    assert second_run["input_snapshots"][0]["source_run_id"] == first_run["run_id"]
    assert second_run["input_snapshots"][0]["source_output_port"] == "result"
    assert second_run["input_snapshots"][0]["artifact"] == first_run["outputs"][0]["artifact"]
    grouped_runs = {
        run["run_id"]: run
        for run in runs.list_runs_for_recipe_execution(result.execution_id)
    }
    assert grouped_runs == {first_run["run_id"]: first_run, second_run["run_id"]: second_run}


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker worker image is built and configured only in the container CI job.",
)
def test_two_node_recipe_executes_upstream_artifact_chain(tmp_path):
    worker = DockerWorker(timeout_seconds=90)
    store, runs, recipes = make_runner(tmp_path, worker)
    source = create_source_artifact(store)
    first, second, _ = make_cell_chain(source)
    capability = load_fixture("capability.valid.json")
    recipe = {
        "recipe_id": "two-buffer-steps",
        "version": "1.0.0",
        "title": "Two sequential buffers",
        "nodes": [
            {"node_id": "second", "cell": {
                "cell_id": second["cell_id"], "version": second["version"]
            }},
            {"node_id": "first", "cell": {
                "cell_id": first["cell_id"], "version": first["version"]
            }},
        ],
        "edges": [
            {
                "from": {"node_id": "first", "output_port": "result"},
                "to": {"node_id": "second", "input_port": "features"},
            }
        ],
        "declared_outputs": [
            {"name": "final", "node_id": "second", "output_port": "result"}
        ],
    }
    cell_map = {
        (cell["cell_id"], cell["version"]): cell for cell in (first, second)
    }
    capability_map = {
        (capability["capability_id"], capability["version"]): capability
    }

    result = recipes.execute(
        recipe=recipe,
        cells=cell_map,
        capabilities=capability_map,
        actor_id="recipe-test",
    )

    assert result.status == "succeeded"
    assert set(result.node_results) == {"first", "second"}
    first_run = result.node_results["first"].run
    second_run = result.node_results["second"].run
    assert first_run["status"] == second_run["status"] == "succeeded"
    assert second_run["input_snapshots"][0]["source_run_id"] == first_run["run_id"]
    assert second_run["input_snapshots"][0]["artifact"] == first_run["outputs"][0]["artifact"]
    assert second["inputs"]["features"]["source"] == "cell_output"
    assert set(result.outputs) == {"final"}
    assert len(runs.list_runs_for_recipe_execution(result.execution_id)) == 2



def test_invalid_recipe_graph_is_rejected_before_any_cell_run(tmp_path):
    worker = SequenceWorker()
    store, runs, recipes = make_runner(tmp_path, worker)
    source = create_source_artifact(store)
    cells = make_cell_chain(source)
    recipe = make_recipe(cells)
    recipe["edges"] = recipe["edges"][:1]
    capability = load_fixture("capability.valid.json")
    cell_map = {(cell["cell_id"], cell["version"]): cell for cell in cells}
    capability_map = {
        (capability["capability_id"], capability["version"]): capability
    }

    with pytest.raises(RecipeExecutionPreconditionError, match="edge_missing"):
        recipes.execute(
            recipe=recipe,
            cells=cell_map,
            capabilities=capability_map,
            actor_id="recipe-test",
        )

    assert not (runs.root / "runs").exists()
    assert worker.calls == 0
