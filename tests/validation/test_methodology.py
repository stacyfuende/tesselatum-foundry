from __future__ import annotations

from tessellatum_foundry.validation.methodology import build_methodology_report


def artifact(artifact_id, crs, geometry_types, metadata=None, bbox=None):
    spatial = {"kind": "vector", "crs": crs, "geometry_types": geometry_types}
    if bbox is not None:
        spatial["bbox"] = bbox
    record = {
        "artifact_id": artifact_id,
        "version": "1.0.0",
        "spatial": spatial,
    }
    if metadata is not None:
        record["metadata"] = metadata
    return record


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
    approximation = findings["method.buffer_arc_approximation"]
    assert approximation["status"] == "passed"
    assert "2.4076 metre" in approximation["message"]
    assert "0.4815%" in approximation["message"]
    assert findings["method.cap_and_join_parameters"]["status"] == "passed"
    assert "buffer_arc_approximation_acceptability" in (
        report["unassessed_dimensions"]
    )
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
        output_artifact=artifact(
            "projected.points",
            target,
            ["Point"],
            metadata={
                "coordinate_operation": {
                    "description": "Popular Visualisation Pseudo-Mercator",
                    "definition": "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad",
                    "accuracy_m": 0.0,
                    "area_of_use": {
                        "west": -180.0,
                        "south": -85.0,
                        "east": 180.0,
                        "north": 85.0,
                        "name": "World",
                    },
                }
            },
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "requires_review"
    assert findings["method.target_crs_explicit_and_matches_output"]["status"] == "passed"
    assert findings["method.ballpark_transformations_disallowed"]["status"] == "passed"
    assert "coordinate_operation_accuracy_suitability" in report["unassessed_dimensions"]
    assert findings["method.coordinate_operation_accuracy_reported"]["status"] == "passed"
    assert findings["method.coordinate_operation_pipeline_recorded"]["status"] == "passed"
    assert findings["method.coordinate_operation_area_of_use_reported"]["status"] == "passed"
    assert findings["method.input_extent_within_operation_area_of_use"]["status"] == "not_assessed"


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
            "wrong.points",
            {"authority": "EPSG", "code": 3857},
            ["Point"],
            metadata={
                "coordinate_operation": {
                    "description": "Popular Visualisation Pseudo-Mercator",
                    "definition": "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad",
                    "accuracy_m": 0.0,
                    "area_of_use": {
                        "west": -180.0,
                        "south": -85.0,
                        "east": 180.0,
                        "north": 85.0,
                        "name": "World",
                    },
                }
            },
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    assert findings["method.target_crs_explicit_and_matches_output"]["status"] == "failed"



def test_buffer_arc_tolerance_passes_when_computed_error_is_within_limit():
    report = build_methodology_report(
        run_id="run:buffer-tolerance-pass",
        cell={
            "constraints": {
                "measurement_crs": {"authority": "EPSG", "code": 32737},
                "linear_unit": "metre",
                "buffer_arc_tolerance": 3.0,
            }
        },
        capability={"capability_id": "vector.buffer"},
        parameters={"distance": 500, "unit": "metre", "quad_segs": 8},
        input_artifact=artifact(
            "source.points", {"authority": "EPSG", "code": 32737}, ["Point"]
        ),
        output_artifact=artifact(
            "buffered.points", {"authority": "EPSG", "code": 32737}, ["Polygon"]
        ),
    )

    findings = findings_by_code(report)
    assert findings["method.buffer_arc_tolerance"]["status"] == "passed"
    assert "2.4076 metre" in findings["method.buffer_arc_tolerance"]["message"]
    assert "buffer_arc_approximation_acceptability" in report["assessed_dimensions"]


def test_buffer_arc_tolerance_fails_when_computed_error_exceeds_limit():
    report = build_methodology_report(
        run_id="run:buffer-tolerance-fail",
        cell={
            "constraints": {
                "measurement_crs": {"authority": "EPSG", "code": 32737},
                "linear_unit": "metre",
                "buffer_arc_tolerance": 1.0,
            }
        },
        capability={"capability_id": "vector.buffer"},
        parameters={"distance": 500, "unit": "metre", "quad_segs": 8},
        input_artifact=artifact(
            "source.points", {"authority": "EPSG", "code": 32737}, ["Point"]
        ),
        output_artifact=artifact(
            "buffered.points", {"authority": "EPSG", "code": 32737}, ["Polygon"]
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    assert findings["method.buffer_arc_tolerance"]["status"] == "failed"



def test_reproject_method_report_requires_actual_operation_evidence():
    report = build_methodology_report(
        run_id="run:missing-operation",
        cell={},
        capability={"capability_id": "vector.reproject"},
        parameters={"target_crs": {"authority": "EPSG", "code": 32737}},
        input_artifact=artifact(
            "source.points", {"authority": "EPSG", "code": 4326}, ["Point"]
        ),
        output_artifact=artifact(
            "projected.points", {"authority": "EPSG", "code": 32737}, ["Point"]
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    assert findings["method.coordinate_operation_identity_recorded"]["status"] == "failed"



def test_coordinate_operation_evidence_accepts_antimeridian_wrapping_area():
    from tessellatum_foundry.validation.methodology import (
        coordinate_operation_evidence_valid,
    )

    assert coordinate_operation_evidence_valid(
        {
            "description": "Pacific operation",
            "accuracy_m": None,
            "area_of_use": {
                "west": 170.0,
                "south": -30.0,
                "east": -170.0,
                "north": 30.0,
                "name": "Dateline region",
            },
        }
    )


def test_coordinate_operation_evidence_rejects_invalid_accuracy_and_bounds():
    from tessellatum_foundry.validation.methodology import (
        coordinate_operation_evidence_valid,
    )

    assert not coordinate_operation_evidence_valid(
        {
            "description": "Invalid operation",
            "accuracy_m": -1.0,
            "area_of_use": None,
        }
    )
    assert not coordinate_operation_evidence_valid(
        {
            "description": "Invalid operation",
            "accuracy_m": 1.0,
            "area_of_use": {
                "west": -200.0,
                "south": -10.0,
                "east": 100.0,
                "north": 10.0,
            },
        }
    )



def test_reproject_method_report_passes_when_geographic_bbox_is_within_operation_area():
    report = build_methodology_report(
        run_id="run:area-covered",
        cell={},
        capability={
            "capability_id": "vector.reproject",
            "preconditions": ["A non-ballpark coordinate operation must be available."],
        },
        parameters={"target_crs": {"authority": "EPSG", "code": 32737}},
        input_artifact=artifact(
            "source.points",
            {"authority": "EPSG", "code": 4326},
            ["Point"],
            bbox=[36.0, -10.0, 42.0, 0.0],
        ),
        output_artifact=artifact(
            "projected.points",
            {"authority": "EPSG", "code": 32737},
            ["Point"],
            metadata={"coordinate_operation": {
                    "description": "UTM zone 37S",
                    "definition": "+proj=pipeline +step +proj=utm +zone=37 +south",
                    "accuracy_m": 0.0,
                    "area_of_use": {
                        "west": 36.0,
                        "south": -80.0,
                        "east": 42.0,
                        "north": 0.0,
                        "name": "UTM zone 37S area",
                    },
                }},
        ),
    )

    findings = findings_by_code(report)
    assert findings["method.input_extent_within_operation_area_of_use"]["status"] == "passed"
    assert "coordinate_operation_area_of_use_coverage" in report["assessed_dimensions"]


def test_reproject_method_report_fails_when_geographic_bbox_exceeds_operation_area():
    report = build_methodology_report(
        run_id="run:area-exceeded",
        cell={},
        capability={
            "capability_id": "vector.reproject",
            "preconditions": ["A non-ballpark coordinate operation must be available."],
        },
        parameters={"target_crs": {"authority": "EPSG", "code": 32737}},
        input_artifact=artifact(
            "source.points",
            {"authority": "EPSG", "code": 4326},
            ["Point"],
            bbox=[43.0, -10.0, 45.0, 0.0],
        ),
        output_artifact=artifact(
            "projected.points",
            {"authority": "EPSG", "code": 32737},
            ["Point"],
            metadata={"coordinate_operation": {
                    "description": "UTM zone 37S",
                    "definition": "+proj=pipeline +step +proj=utm +zone=37 +south",
                    "accuracy_m": 0.0,
                    "area_of_use": {
                        "west": 36.0,
                        "south": -80.0,
                        "east": 42.0,
                        "north": 0.0,
                        "name": "UTM zone 37S area",
                    },
                }},
        ),
    )

    findings = findings_by_code(report)
    assert report["overall_status"] == "failed"
    coverage = findings["method.input_extent_within_operation_area_of_use"]
    assert coverage["status"] == "failed"
    assert coverage["severity"] == "warning"



def test_reproject_method_report_leaves_invalid_geographic_bbox_unassessed():
    report = build_methodology_report(
        run_id="run:invalid-area-bbox",
        cell={},
        capability={"capability_id": "vector.reproject"},
        parameters={"target_crs": {"authority": "EPSG", "code": 3857}},
        input_artifact=artifact(
            "source.points",
            {"authority": "EPSG", "code": 4326},
            ["Point"],
            bbox=[-200.0, -5.0, 179.0, 5.0],
        ),
        output_artifact=artifact(
            "projected.points",
            {"authority": "EPSG", "code": 3857},
            ["Point"],
            metadata={
                "coordinate_operation": {
                    "description": "World operation",
                    "definition": "+proj=pipeline +step +proj=merc",
                    "accuracy_m": 1.0,
                    "area_of_use": {
                        "west": -180.0,
                        "south": -85.0,
                        "east": 180.0,
                        "north": 85.0,
                        "name": "World",
                    },
                }
            },
        ),
    )

    coverage = findings_by_code(report)[
        "method.input_extent_within_operation_area_of_use"
    ]
    assert coverage["status"] == "not_assessed"


def test_reproject_method_report_handles_antimeridian_wrapping_operation_area():
    report = build_methodology_report(
        run_id="run:wrapped-area",
        cell={},
        capability={"capability_id": "vector.reproject"},
        parameters={"target_crs": {"authority": "EPSG", "code": 3857}},
        input_artifact=artifact(
            "source.points",
            {"authority": "EPSG", "code": 4326},
            ["Point"],
            bbox=[175.0, -5.0, 179.0, 5.0],
        ),
        output_artifact=artifact(
            "projected.points",
            {"authority": "EPSG", "code": 3857},
            ["Point"],
            metadata={
                "coordinate_operation": {
                    "description": "Dateline operation",
                    "definition": "+proj=pipeline +step +proj=merc",
                    "accuracy_m": 1.0,
                    "area_of_use": {
                        "west": 170.0,
                        "south": -10.0,
                        "east": -170.0,
                        "north": 10.0,
                        "name": "Dateline region",
                    },
                }
            },
        ),
    )

    findings = findings_by_code(report)
    assert findings["method.input_extent_within_operation_area_of_use"]["status"] == "passed"
