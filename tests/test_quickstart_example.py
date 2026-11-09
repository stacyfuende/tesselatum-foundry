from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.graph import validate_recipe_graph
from tessellatum_foundry.validation.spatial import validate_recipe_spatial

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "quickstart"


def _load(name: str) -> dict:
    return json.loads((EXAMPLE / name).read_text(encoding="utf-8"))


def test_quickstart_example_contract_graph_and_spatial_preflight():
    contracts = ContractRegistry()
    capabilities = CapabilityRegistry()
    cell = _load("buffer.cell.json")
    recipe = _load("buffer.recipe.json")
    spatial = _load("sites.spatial.json")
    feature_collection = _load("sites.geojson")

    contracts.validate("cell.schema.json", cell)
    contracts.validate("recipe.schema.json", recipe)
    capability = capabilities.get("vector.buffer", "1.0.0")
    cells = {(cell["cell_id"], cell["version"]): cell}
    capability_map = {(capability["capability_id"], capability["version"]): capability}
    artifact_ref = ("quickstart.sites", "1.0.0")
    artifact = {
        "artifact_id": artifact_ref[0],
        "version": artifact_ref[1],
        "spatial": spatial,
    }

    graph_findings = validate_recipe_graph(
        recipe,
        cells=cells,
        capabilities=capability_map,
        artifacts={artifact_ref},
    )
    spatial_findings = validate_recipe_spatial(
        recipe,
        cells=cells,
        capabilities=capability_map,
        artifacts={artifact_ref: artifact},
    )

    assert graph_findings == []
    assert spatial_findings == []
    assert feature_collection["type"] == "FeatureCollection"
    assert len(feature_collection["features"]) == 2
    assert {
        feature["geometry"]["type"] for feature in feature_collection["features"]
    } == {"Polygon"}
