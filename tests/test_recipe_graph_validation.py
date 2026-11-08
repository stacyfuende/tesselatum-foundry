from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry.validation import validate_recipe_graph

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def base_context():
    cell = load_fixture("cell.valid.json")
    capability = load_fixture("capability.valid.json")
    recipe = load_fixture("recipe.valid.json")
    return recipe, {(cell["cell_id"], cell["version"]): cell}, {
        (capability["capability_id"], capability["version"]): capability
    }


def test_valid_single_node_recipe_has_no_semantic_findings():
    recipe, cells, capabilities = base_context()
    artifacts = {("dataset.buildings", "1.0.0")}
    assert validate_recipe_graph(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    ) == []


def test_missing_required_input_is_reported():
    recipe, cells, capabilities = base_context()
    cell = dict(next(iter(cells.values())))
    cell["inputs"] = {}
    cells[(cell["cell_id"], cell["version"])] = cell
    findings = validate_recipe_graph(recipe, cells=cells, capabilities=capabilities)
    assert "cell.required_input_unbound" in {finding.code for finding in findings}


def test_invalid_parameters_are_reported():
    recipe, cells, capabilities = base_context()
    cell = dict(next(iter(cells.values())))
    cell["parameters"] = {"distance": -5, "unit": "metre"}
    cells[(cell["cell_id"], cell["version"])] = cell
    findings = validate_recipe_graph(recipe, cells=cells, capabilities=capabilities)
    assert "cell.parameters_invalid" in {finding.code for finding in findings}


def test_missing_artifact_reference_is_reported():
    recipe, cells, capabilities = base_context()
    findings = validate_recipe_graph(
        recipe, cells=cells, capabilities=capabilities, artifacts=set()
    )
    assert "cell.artifact_not_found" in {finding.code for finding in findings}


def test_cell_output_binding_requires_matching_recipe_edge():
    recipe, cells, capabilities = base_context()
    source = dict(next(iter(cells.values())))
    source["cell_id"] = "source-cell"
    source["inputs"] = {"features": {"source": "artifact", "artifact": {
        "artifact_id": "dataset.buildings", "version": "1.0.0"
    }}}
    target = dict(next(iter(cells.values())))
    target["cell_id"] = "target-cell"
    target["inputs"] = {"features": {"source": "cell_output", "cell_id": "source-cell",
                                     "cell_version": "1.0.0", "output_port": "result"}}
    cells = {
        (source["cell_id"], source["version"]): source,
        (target["cell_id"], target["version"]): target,
    }
    recipe = {
        "recipe_id": "two-step", "version": "1.0.0", "title": "Two step",
        "nodes": [
            {"node_id": "source", "cell": {"cell_id": "source-cell", "version": "1.0.0"}},
            {"node_id": "target", "cell": {"cell_id": "target-cell", "version": "1.0.0"}},
        ],
        "edges": [],
        "declared_outputs": [{"name": "result", "node_id": "target", "output_port": "result"}],
    }
    findings = validate_recipe_graph(recipe, cells=cells, capabilities=capabilities)
    assert "recipe.edge_missing" in {finding.code for finding in findings}


def test_recipe_cycle_is_reported():
    recipe, cells, capabilities = base_context()
    left = dict(next(iter(cells.values())))
    left["cell_id"] = "left-cell"
    right = dict(next(iter(cells.values())))
    right["cell_id"] = "right-cell"
    left["inputs"] = {"features": {"source": "cell_output", "cell_id": "right-cell",
                                   "cell_version": "1.0.0", "output_port": "result"}}
    right["inputs"] = {"features": {"source": "cell_output", "cell_id": "left-cell",
                                    "cell_version": "1.0.0", "output_port": "result"}}
    cells = {
        (left["cell_id"], left["version"]): left,
        (right["cell_id"], right["version"]): right,
    }
    recipe = {
        "recipe_id": "cycle", "version": "1.0.0", "title": "Cycle",
        "nodes": [
            {"node_id": "left", "cell": {"cell_id": "left-cell", "version": "1.0.0"}},
            {"node_id": "right", "cell": {"cell_id": "right-cell", "version": "1.0.0"}},
        ],
        "edges": [
            {"from": {"node_id": "left", "output_port": "result"},
             "to": {"node_id": "right", "input_port": "features"}},
            {"from": {"node_id": "right", "output_port": "result"},
             "to": {"node_id": "left", "input_port": "features"}},
        ],
        "declared_outputs": [],
    }
    findings = validate_recipe_graph(recipe, cells=cells, capabilities=capabilities)
    assert "recipe.cycle_detected" in {finding.code for finding in findings}
