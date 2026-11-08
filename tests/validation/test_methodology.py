from __future__ import annotations

from tessellatum_foundry.validation.methodology import build_methodology_report


def artifact(artifact_id, crs, geometry_types):
    return {
        "artifact_id": artifact_id,
        "version": "1.0.0",
        "spatial": {"kind": "vector", "crs": crs, "geometry_types": geometry_types},
    }


def findings_by_code(report):
    return {finding["code"]: finding for finding in report["findings"]}


def test_buffer_method_report_assesses_planar_measurement_and_exposes_limits():
    input_artifact = artifact(
        "source.points",
        {"authority": "EPSG", "code": 32737},
        ["Point"],
    )
    output_artifact = artifact(
        "buffered.points",
        {"authority": "EPSG", "code": 32737},
        ["Polygon"],
    )
    cell = {
        "constraints": {
            "measurement_crs": {"authority": "EPSG", "code": 32737},
        }
    }
    capability = {
        "capability_id": "vector.buffer",
        "description": "Construct planar buffers using a projected measurement CRS.",
    }
    parameters = {"distance": 500, "unit": "metre", "single_sided": False}

    report = build_methodology_report(
        run_id="run:buffer",
        cell=cell,
        capability=capability,
        parameters=parameters,
        input_artifact=input_artifact,
        output_artifact=output_artifact,
    )

    findings = findings_by_code(report)
    assert report["stage"] == "methodological"
    assert report["overall_status"] == "requires_review"
    assert findings["method.measurement_crs_projected"]["status"] == "passed"
    assert findings["method.input_crs_matches_measurement_crs"]["status"] == "passed"
    assert findings["method.distance_unit_matches_crs"]["status"] == "passed"
    assert "projection_scale_distortion_over_area_of_interest" in (
        report["unassessed_dimensions"]
    )


def test_buffer_method_report_fails_incompatible_measurement_declarations():
    input_artifact = artifact(
        "source.points",
        {"authority": "EPSG", "code": 4326},
        ["Point"],
    )
    output_artifact = artifact(
        "buffered.points",
        {"authority": "EPSG", "code": 4326},
        ["Polygon"],
    )
    report = build_methodology_report(
        run_id="run:bad-buffer",
        cell={
            "constraints": {
                "measurement_crs": {"authority": "EPSG", "code": 4326},
            }
        },
        capability={"capability_id": "vector.buffer"},
        parameters={"distance": 500, "unit": "metre"},
        input_artifact=input_artifact,
        output_artifact=output_artifact,
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    assert findings["method.measurement_crs_projected"]["status"] == "failed"


def test_reproject_report_records_non_ballpark_contract_and_unassessed_accuracy():
    source = {"authority": "EPSG", "code": 4326}
    target = {"authority": "EPSG", "code": 32737}
    report = build_methodology_report(
        run_id="run:reproject",
        cell={},
        capability={
            "capability_id": "vector.reproject",
            "preconditions": [
                "A non-ballpark coordinate operation must be available.",
                (
                    "The operation does not repair geometries, densify segments, "
                    "clip extents, or split antimeridian crossings."
                ),
            ],
        },
        parameters={"target_crs": target},
        input_artifact=artifact("source.points", source, ["Point"]),
        output_artifact=artifact("projected.points", target, ["Point"]),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "requires_review"
    assert findings["method.target_crs_explicit_and_matches_output"]["status"] == "passed"
    assert findings["method.ballpark_transformations_disallowed"]["status"] == "passed"
    assert "coordinate_operation_accuracy" in report["unassessed_dimensions"]


def test_reproject_report_fails_when_output_crs_differs_from_target():
    report = build_methodology_report(
        run_id="run:wrong-output",
        cell={},
        capability={"capability_id": "vector.reproject"},
        parameters={"target_crs": {"authority": "EPSG", "code": 32737}},
        input_artifact=artifact(
            "source.points", {"authority": "EPSG", "code": 4326}, ["Point"]
        ),
        output_artifact=artifact(
            "wrong.points", {"authority": "EPSG", "code": 3857}, ["Point"]
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    assert findings["method.target_crs_explicit_and_matches_output"]["status"] == "failed"
