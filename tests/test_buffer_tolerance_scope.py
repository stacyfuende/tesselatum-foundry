from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry.validation import validate_recipe_spatial


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_buffer_arc_tolerance_is_rejected_for_non_buffer_capabilities():
    artifact = load_fixture("artifact.valid.json")
    capability = load_fixture("capability.valid.json")
    cell = load_fixture("cell.valid.json")
    recipe = load_fixture("recipe.valid.json")
    cell["constraints"]["buffer_arc_tolerance"] = 2.0
    cell["capability"] = {
        "capability_id": "vector.reproject",
        "version": "1.0.0",
    }
    capability["capability_id"] = "vector.reproject"

    findings = validate_recipe_spatial(
        recipe,
        cells={(cell["cell_id"], cell["version"]): cell},
        capabilities={
            (capability["capability_id"], capability["version"]): capability
        },
        artifacts={(artifact["artifact_id"], artifact["version"]): artifact},
    )

    assert "spatial.buffer_arc_tolerance_wrong_capability" in {
        finding.code for finding in findings
    }
