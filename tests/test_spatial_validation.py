from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry.validation import (
    validate_artifact_spatial_metadata,
    validate_recipe_spatial,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def spatial_context():
    artifact = load_fixture("artifact.valid.json")
    capability = load_fixture("capability.valid.json")
    cell = load_fixture("cell.valid.json")
    recipe = load_fixture("recipe.valid.json")
    return (
        recipe,
        {(cell["cell_id"], cell["version"]): cell},
        {(capability["capability_id"], capability["version"]): capability},
        {(artifact["artifact_id"], artifact["version"]): artifact},
    )


def finding_codes(findings):
    return {finding.code for finding in findings}


def test_valid_spatial_recipe_has_no_findings():
    recipe, cells, capabilities, artifacts = spatial_context()
    assert validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    ) == []


def test_vector_artifact_requires_crs():
    artifact = load_fixture("artifact.valid.json")
    del artifact["spatial"]["crs"]
    findings = validate_artifact_spatial_metadata(artifact)
    assert "spatial.crs_missing" in finding_codes(findings)


def test_invalid_crs_is_reported():
    artifact = load_fixture("artifact.valid.json")
    artifact["spatial"]["crs"] = {"authority": "EPSG", "code": 99999999}
    findings = validate_artifact_spatial_metadata(artifact)
    assert "spatial.crs_invalid" in finding_codes(findings)


def test_geographic_extent_rejects_latitude_outside_domain():
    artifact = load_fixture("artifact.valid.json")
    artifact["spatial"]["bbox"] = [36.7, -95.0, 37.1, -1.0]
    findings = validate_artifact_spatial_metadata(artifact)
    assert "spatial.bbox_latitude_out_of_range" in finding_codes(findings)


def test_reversed_extent_is_reported():
    artifact = load_fixture("artifact.valid.json")
    artifact["spatial"]["bbox"] = [37.1, -1.4, 36.7, -1.0]
    findings = validate_artifact_spatial_metadata(artifact)
    assert "spatial.bbox_axis_reversed" in finding_codes(findings)


def test_non_finite_extent_is_reported():
    artifact = load_fixture("artifact.valid.json")
    artifact["spatial"]["bbox"] = [36.7, -1.4, float("inf"), -1.0]
    findings = validate_artifact_spatial_metadata(artifact)
    assert "spatial.bbox_non_finite" in finding_codes(findings)


def test_vector_artifact_requires_geometry_type_metadata_when_port_requires_it():
    recipe, cells, capabilities, artifacts = spatial_context()
    del artifacts[("dataset.buildings", "1.0.0")]["spatial"]["geometry_types"]
    capabilities[("vector.buffer", "1.0.0")]["input_ports"][0]["spatial"] = {
        "geometry_types": ["Polygon"]
    }
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.input_geometry_types_missing" in finding_codes(findings)


def test_input_geometry_type_must_satisfy_capability_port():
    recipe, cells, capabilities, artifacts = spatial_context()
    capabilities[("vector.buffer", "1.0.0")]["input_ports"][0]["spatial"] = {
        "geometry_types": ["Point"]
    }
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.input_geometry_type_mismatch" in finding_codes(findings)


def test_input_crs_type_must_satisfy_capability_port():
    recipe, cells, capabilities, artifacts = spatial_context()
    capabilities[("vector.buffer", "1.0.0")]["input_ports"][0]["spatial"] = {
        "crs_type": "projected"
    }
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.input_crs_type_mismatch" in finding_codes(findings)


def test_measurement_crs_must_be_projected_for_linear_units():
    recipe, cells, capabilities, artifacts = spatial_context()
    cell = cells[("buffer-buildings", "1.0.0")]
    cell["constraints"]["measurement_crs"] = {
        "authority": "EPSG",
        "code": 4326,
    }
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.measurement_crs_not_projected" in finding_codes(findings)


def test_linear_unit_must_match_measurement_crs_axes():
    recipe, cells, capabilities, artifacts = spatial_context()
    cell = cells[("buffer-buildings", "1.0.0")]
    cell["constraints"]["linear_unit"] = "foot"
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.linear_unit_mismatch" in finding_codes(findings)


def test_measurement_unit_requires_measurement_crs():
    recipe, cells, capabilities, artifacts = spatial_context()
    cell = cells[("buffer-buildings", "1.0.0")]
    del cell["constraints"]["measurement_crs"]
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.measurement_crs_required" in finding_codes(findings)


def test_input_port_data_kind_must_match_artifact_spatial_kind():
    recipe, cells, capabilities, artifacts = spatial_context()
    artifacts[("dataset.buildings", "1.0.0")]["spatial"]["kind"] = "raster"
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.input_kind_mismatch" in finding_codes(findings)


def test_output_contract_requires_resolvable_crs():
    recipe, cells, capabilities, artifacts = spatial_context()
    cells[("buffer-buildings", "1.0.0")]["output_contracts"]["result"]["crs"] = {
        "authority": "EPSG",
        "code": 99999999,
    }
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.output_crs_invalid" in finding_codes(findings)


def test_input_ports_can_require_equivalent_crs():
    recipe, cells, capabilities, artifacts = spatial_context()
    cell = cells[("buffer-buildings", "1.0.0")]
    cell["inputs"]["boundary"] = {
        "source": "artifact",
        "artifact": {"artifact_id": "dataset.boundary", "version": "1.0.0"},
    }
    boundary = load_fixture("artifact.valid.json")
    boundary["artifact_id"] = "dataset.boundary"
    boundary["spatial"]["crs"] = {"authority": "EPSG", "code": 32637}
    artifacts[("dataset.boundary", "1.0.0")] = boundary
    capability = capabilities[("vector.buffer", "1.0.0")]
    capability["input_ports"].append(
        {
            "port_id": "boundary",
            "data_kind": "vector",
            "required": False,
            "spatial": {"same_crs_as": "features"},
        }
    )
    findings = validate_recipe_spatial(
        recipe, cells=cells, capabilities=capabilities, artifacts=artifacts
    )
    assert "spatial.input_crs_mismatch" in finding_codes(findings)
