"""Evidence for operation-specific analytical assumptions and limitations."""

from __future__ import annotations

import math
from typing import Any

from pyproj import CRS
from pyproj.exceptions import CRSError

from tessellatum_foundry.storage.artifacts import utc_timestamp


_VALIDATOR_NAME = "foundry-methodology-critic"
_VALIDATOR_VERSION = "0.1.0"

_UNIT_ALIASES = {
    "m": "metre",
    "meter": "metre",
    "meters": "metre",
    "metres": "metre",
    "ft": "foot",
    "feet": "foot",
    "foot": "foot",
    "us survey foot": "us survey foot",
}


def _unit_name(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").split())
    return _UNIT_ALIASES.get(normalized, normalized)


def _resolve_crs(value: Any) -> CRS:
    if not isinstance(value, dict):
        raise ValueError("CRS declaration must be an object.")
    if "authority" in value and "code" in value:
        return CRS.from_authority(str(value["authority"]), str(value["code"]))
    if "wkt2" in value:
        return CRS.from_wkt(value["wkt2"])
    raise ValueError("CRS declaration must contain authority/code or WKT2.")


def _finding(
    code: str,
    status: str,
    message: str,
    *,
    severity: str = "info",
    evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "status": status,
        "message": message,
    }
    if evidence:
        finding["evidence"] = evidence
    return finding


def build_methodology_report(
    *,
    run_id: str,
    cell: dict[str, Any],
    capability: dict[str, Any],
    parameters: dict[str, Any],
    input_artifact: dict[str, Any],
    output_artifact: dict[str, Any],
) -> dict[str, Any]:
    """Record validated operation semantics and what suitability remains unknown.

    This critic does not infer analytical purpose, acceptable error, or
    suitability from a CRS name. It assesses only declarations and semantics
    that the current capability contract makes explicit.
    """
    capability_id = capability["capability_id"]
    input_ref = (
        f"{input_artifact['artifact_id']}@{input_artifact['version']}"
    )
    output_ref = (
        f"{output_artifact['artifact_id']}@{output_artifact['version']}"
    )
    evidence = [
        {
            "kind": "artifact",
            "reference": input_ref,
            "summary": "Exact immutable input Artifact used by this Run.",
        },
        {
            "kind": "artifact",
            "reference": output_ref,
            "summary": "Exact output Artifact produced or reused by this Run.",
        },
    ]
    findings: list[dict[str, Any]] = []
    assessed_dimensions = ["declared_operation_semantics"]
    unassessed: list[str] = [
        "analysis_purpose",
        "acceptable_error_tolerance",
    ]

    if capability_id == "vector.buffer":
        try:
            input_crs = _resolve_crs(input_artifact["spatial"]["crs"])
            measurement_crs = _resolve_crs(cell["constraints"]["measurement_crs"])
            projected = measurement_crs.is_projected
            crs_matches = input_crs.equals(
                measurement_crs, ignore_axis_order=True
            )
            output_crs = _resolve_crs(output_artifact["spatial"]["crs"])
            output_matches = output_crs.equals(
                measurement_crs, ignore_axis_order=True
            )
            axes = measurement_crs.axis_info[:2]
            axis_units = [_unit_name(axis.unit_name or "") for axis in axes]
            declared_unit = _unit_name(str(parameters["unit"]))
            unit_matches = (
                len(axis_units) == 2
                and axis_units[0] == axis_units[1] == declared_unit
            )
            distance = parameters["distance"]
            distance_valid = (
                isinstance(distance, (int, float))
                and not isinstance(distance, bool)
                and math.isfinite(distance)
                and distance > 0
            )
        except (CRSError, KeyError, TypeError, ValueError, OverflowError):
            projected = crs_matches = output_matches = False
            unit_matches = distance_valid = False
            axis_units = []
            declared_unit = str(parameters.get("unit", "unknown"))

        checks = [
            (
                "method.measurement_crs_projected",
                projected,
                "The declared measurement CRS is projected for planar distance measurement.",
            ),
            (
                "method.input_crs_matches_measurement_crs",
                crs_matches,
                "The input coordinates already use the declared measurement CRS.",
            ),
            (
                "method.output_crs_matches_measurement_crs",
                output_matches,
                "The output Artifact remains in the declared measurement CRS.",
            ),
            (
                "method.distance_unit_matches_crs",
                unit_matches,
                "The distance unit matches both horizontal measurement CRS axis units.",
            ),
            (
                "method.distance_positive_and_finite",
                distance_valid,
                "The requested planar buffer distance is finite and positive.",
            ),
        ]
        for code, passed, message in checks:
            findings.append(
                _finding(
                    code,
                    "passed" if passed else "failed",
                    message,
                    severity="error" if not passed else "info",
                    evidence=evidence,
                )
            )
        findings.append(
            _finding(
                "method.planar_buffer_semantics",
                "passed",
                (
                    "The capability explicitly performs planar buffering in the "
                    f"declared measurement CRS using {parameters.get('distance')} "
                    f"{parameters.get('unit')}."
                ),
                evidence=evidence,
            )
        )
        if parameters.get("single_sided", False):
            line_only = set(
                input_artifact.get("spatial", {}).get("geometry_types", [])
            ) == {"LineString"}
            findings.append(
                _finding(
                    "method.single_sided_left_side",
                    "passed" if line_only else "failed",
                    "Single-sided buffering selects the left side of LineString inputs.",
                    severity="error" if not line_only else "info",
                    evidence=evidence,
                )
            )
        assessed_dimensions.extend(["measurement_crs_and_units", "planar_distance_model"])
        unassessed.extend(
            [
                "projection_scale_distortion_over_area_of_interest",
                "distance_accuracy_for_intended_purpose",
                "geodesic_distance_suitability",
            ]
        )
    elif capability_id == "vector.reproject":
        try:
            _resolve_crs(input_artifact["spatial"]["crs"])
            source_crs_resolved = True
        except (CRSError, KeyError, TypeError, ValueError, OverflowError):
            source_crs_resolved = False
        try:
            target_crs = _resolve_crs(parameters["target_crs"])
            output_crs = _resolve_crs(output_artifact["spatial"]["crs"])
            target_matches_output = target_crs.equals(
                output_crs, ignore_axis_order=True
            )
        except (CRSError, KeyError, TypeError, ValueError, OverflowError):
            target_matches_output = False

        preconditions = [
            str(item).lower() for item in capability.get("preconditions", [])
        ]
        non_ballpark_declared = any(
            "non-ballpark" in item for item in preconditions
        )
        no_densification_declared = any(
            "does not" in item and "densify segments" in item
            for item in preconditions
        )
        no_antimeridian_split_declared = any(
            "does not" in item and "split antimeridian" in item
            for item in preconditions
        )
        findings.extend(
            [
                _finding(
                    "method.source_crs_explicit_and_resolvable",
                    "passed" if source_crs_resolved else "failed",
                    "The input Artifact declares a resolvable source CRS.",
                    severity="error" if not source_crs_resolved else "info",
                    evidence=evidence,
                ),
                _finding(
                    "method.target_crs_explicit_and_matches_output",
                    "passed" if target_matches_output else "failed",
                    "The explicit target CRS matches the output Artifact CRS.",
                    severity="error" if not target_matches_output else "info",
                    evidence=evidence,
                ),
                _finding(
                    "method.ballpark_transformations_disallowed",
                    "passed" if non_ballpark_declared else "not_assessed",
                    (
                        "The capability requires a non-ballpark coordinate operation; "
                        "this is not a measurement of achieved positional accuracy."
                    ),
                    evidence=evidence,
                ),
                _finding(
                    "method.segment_densification_not_performed",
                    "passed" if no_densification_declared else "not_assessed",
                    (
                        "The capability transforms stored vertices and does not densify "
                        "segments; curved-edge approximation is therefore not evaluated."
                    ),
                    severity="warning",
                    evidence=evidence,
                ),
                _finding(
                    "method.antimeridian_splitting_not_performed",
                    "passed" if no_antimeridian_split_declared else "not_assessed",
                    (
                        "The capability does not split antimeridian crossings; "
                        "datasets crossing that discontinuity require separate handling."
                    ),
                    severity="warning",
                    evidence=evidence,
                ),
            ]
        )
        assessed_dimensions.extend(["source_and_target_crs", "transformation_limitations"])
        unassessed.extend(
            [
                "coordinate_operation_accuracy",
                "coordinate_operation_area_of_use",
                "segment_shape_error_without_densification",
                "antimeridian_crossing_suitability",
            ]
        )
    else:
        findings.append(
            _finding(
                "method.capability_not_assessed",
                "not_assessed",
                f"No operation-specific methodology critic exists for {capability_id!r}.",
                severity="warning",
            )
        )
        unassessed.append("operation_specific_methodology")

    failed = any(finding["status"] == "failed" for finding in findings)
    overall_status = "failed" if failed else "requires_review"
    return {
        "report_id": f"report:{run_id}:methodology",
        "subject": {"kind": "run", "id": run_id},
        "stage": "methodological",
        "overall_status": overall_status,
        "created_at": utc_timestamp(),
        "validator": {
            "name": _VALIDATOR_NAME,
            "version": _VALIDATOR_VERSION,
        },
        "findings": findings,
        "summary": (
            "Declared operation semantics were assessed. Analytical suitability "
            "remains subject to the unassessed purpose, accuracy, and area-of-use "
            "dimensions listed in this report."
        ),
        "assessed_dimensions": assessed_dimensions,
        "unassessed_dimensions": sorted(set(unassessed)),
    }
