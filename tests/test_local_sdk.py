from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry import LocalFoundry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_local_sdk_registers_and_reads_exact_definition_versions(tmp_path):
    foundry = LocalFoundry(tmp_path)
    cell = load_fixture("cell.valid.json")
    recipe = load_fixture("recipe.valid.json")

    cell_record = foundry.register_cell(cell, created_by="sdk-test")
    recipe_record = foundry.register_recipe(recipe, created_by="sdk-test")

    assert foundry.definitions.get_cell(cell["cell_id"], cell["version"]) == cell
    assert foundry.definitions.get_recipe(recipe["recipe_id"], recipe["version"]) == recipe
    assert cell_record["definition_ref"]["definition_id"] == cell["cell_id"]
    assert recipe_record["definition_ref"]["definition_id"] == recipe["recipe_id"]
    assert foundry.capabilities.get("vector.buffer", "1.0.0")["capability_id"] == "vector.buffer"
    assert foundry.implementations.require_conformant(
        implementation_id="vector-buffer-shapely",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )["conformance"]["status"] == "passed"


def test_local_sdk_exposes_persisted_artifact_store(tmp_path):
    foundry = LocalFoundry(tmp_path)
    content = {
        "type": "FeatureCollection",
        "features": [],
    }
    artifact = foundry.artifacts.put_bytes(
        artifact_id="empty.features",
        version="1.0.0",
        content=json.dumps(content).encode(),
        created_by="sdk-test",
        media_type=(
            "application/vnd.tessellatum.spatial-feature-collection+json"
        ),
        format_name="Foundry Spatial Feature Collection JSON",
        spatial={
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 32737},
            "geometry_types": ["Point"],
        },
    )

    retrieved = foundry.get_artifact("empty.features", "1.0.0")

    assert retrieved == artifact
    assert json.loads(foundry.read_artifact(retrieved)) == content
