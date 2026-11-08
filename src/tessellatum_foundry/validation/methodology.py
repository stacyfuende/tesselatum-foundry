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


def _finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def coordinate_operation_evidence_valid(value: Any) -> bool:
    """Validate the bounded metadata envelope returned by the reprojection worker."""
    if not isinstance(value, dict):
        return False
    description = value.get("description")
    if not isinstance(description, str) or not description.strip():
        return False
    if len(description) > 2048:
        return False
    definition = value.get("definition")
    if definition is not None and (
        not isinstance(definition, str)
        or not definition.strip()
        or len(definition) > 8192
    ):
        return False
    accuracy = value.get("accuracy_m")
    if accuracy is not None:
        if (
            not _finite_number(accuracy)
            or accuracy < 0
        ):
            return False
    area = value.get("area_of_use")
    if area is not None:
        if not isinstance(area, dict):
            return False
        bounds = [area.get(key) for key in ("west", "south", "east", "north")]
        if any(
            not _finite_number(bound)
            for bound in bounds
        ):
            return False
        west, south, east, north = bounds
        if (
            west < -180
            or east > 180
            or south < -90
            or north > 90
            or south > north
        ):
            return False
        name = area.get("name")
        if name is not None and not isinstance(name, str):
            return False
    return True


def _geographic_bbox_within_area_of_use(
    bbox: Any,
    area: dict[str, Any],
) -> bool | None:
    """Compare a GIS-order geographic bbox with PROJ longitude/latitude bounds."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) not in {4, 6}:
        return None
    if any(not _finite_number(value) for value in bbox):
        return None
    if len(bbox) == 4:
        min_x, min_y, max_x, max_y = bbox
    else:
        min_x, min_y, _, max_x, max_y, _ = bbox
    if min_x > max_x or min_y > max_y:
        return None

    west = area["west"]
    south = area["south"]
    east = area["east"]
    north = area["north"]
    if west <= east:
        longitude_covered = min_x >= west and max_x <= east
    else:
        longitude_covered = (
            (min_x >= west and max_x <= 180)
            or (min_x >= -180 and max_x <= east)
        )
    latitude_covered = min_y >= south and max_y <= north
    return longitude_covered and latitude_covered


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
        quad_segs = parameters.get("quad_segs", 8)
        quad_segs_valid = (
            isinstance(quad_segs, int)
            and not isinstance(quad_segs, bool)
            and 1 <= quad_segs <= 64
        )
        if quad_segs_valid and distance_valid:
            relative_sagitta = 1.0 - math.cos(math.pi / (4.0 * quad_segs))
            absolute_sagitta = float(distance) * relative_sagitta
            approximation_message = (
                f"quad_segs={quad_segs} gives a maximum radial sagitta of "
                f"{absolute_sagitta:.4f} {parameters.get('unit')} "
                f"({relative_sagitta * 100:.4f}% of the requested radius)."
            )
        else:
            absolute_sagitta = None
            approximation_message = (
                "Arc approximation error could not be computed because the "
                "distance or quad_segs parameter is invalid."
            )
        constraints = cell.get("constraints", {})
        arc_tolerance = constraints.get("buffer_arc_tolerance")
        tolerance_unit_matches = (
            constraints.get("linear_unit") is not None
            and _unit_name(str(constraints.get("linear_unit")))
            == _unit_name(str(parameters.get("unit", "")))
        )
        if arc_tolerance is None:
            tolerance_status = "not_assessed"
            tolerance_message = (
                "No buffer_arc_tolerance is declared; approximation acceptability "
                "remains unassessed."
            )
        else:
            try:
                tolerance_valid = (
                    isinstance(arc_tolerance, (int, float))
                    and not isinstance(arc_tolerance, bool)
                    and math.isfinite(arc_tolerance)
                    and arc_tolerance > 0
                )
            except OverflowError:
                tolerance_valid = False
            if not tolerance_valid or not tolerance_unit_matches:
                tolerance_status = "failed"
                tolerance_message = (
                    "buffer_arc_tolerance must be finite, positive, and expressed "
                    "in the same linear_unit as the buffer distance."
                )
            elif absolute_sagitta is None:
                tolerance_status = "not_assessed"
                tolerance_message = (
                    "The declared tolerance could not be evaluated because the "
                    "arc approximation parameters are invalid."
                )
            else:
                tolerance_status = (
                    "passed" if absolute_sagitta <= arc_tolerance else "failed"
                )
                tolerance_message = (
                    f"Computed radial sagitta {absolute_sagitta:.4f} "
                    f"{parameters.get('unit')} versus declared tolerance "
                    f"{arc_tolerance:.4f} {constraints['linear_unit']}."
                )
        cap_style = parameters.get("cap_style", "round")
        join_style = parameters.get("join_style", "round")
        mitre_limit = parameters.get("mitre_limit", 5.0)
        try:
            mitre_limit_valid = (
                isinstance(mitre_limit, (int, float))
                and not isinstance(mitre_limit, bool)
                and math.isfinite(mitre_limit)
                and mitre_limit > 0
            )
        except OverflowError:
            mitre_limit_valid = False
        cap_join_valid = (
            isinstance(cap_style, str)
            and cap_style in {"round", "flat", "square"}
            and isinstance(join_style, str)
            and join_style in {"round", "mitre", "bevel"}
            and mitre_limit_valid
        )
        findings.extend(
            [
                _finding(
                    "method.quad_segs_valid",
                    "passed" if quad_segs_valid else "failed",
                    "quad_segs is an integer from 1 through 64.",
                    severity="error" if not quad_segs_valid else "info",
                    evidence=evidence,
                ),
                _finding(
                    "method.buffer_arc_approximation",
                    "passed" if absolute_sagitta is not None else "not_assessed",
                    approximation_message,
                    severity="info",
                    evidence=evidence,
                ),
                _finding(
                    "method.buffer_arc_tolerance",
                    tolerance_status,
                    tolerance_message,
                    severity=(
                        "error" if tolerance_status == "failed" else "warning"
                    ),
                    evidence=evidence,
                ),
                _finding(
                    "method.cap_and_join_parameters",
                    "passed" if cap_join_valid else "failed",
                    (
                        f"cap_style={cap_style!r}, join_style={join_style!r}; "
                        + (
                            f"mitre_limit={mitre_limit} applies."
                            if join_style == "mitre"
                            else f"mitre_limit={mitre_limit} is inactive for this join style."
                        )
                    ),
                    severity="error" if not cap_join_valid else "info",
                    evidence=evidence,
                ),
            ]
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
        assessed_dimensions.extend([
            "measurement_crs_and_units",
            "planar_distance_model",
        ])
        if absolute_sagitta is not None:
            assessed_dimensions.append("buffer_arc_approximation_metric")
        if tolerance_status == "passed" or tolerance_status == "failed":
            assessed_dimensions.append("buffer_arc_approximation_acceptability")
        else:
            unassessed.append("buffer_arc_approximation_acceptability")
        unassessed.extend(
            [
                "projection_scale_distortion_over_area_of_interest",
                "distance_accuracy_for_intended_purpose",
                "geodesic_distance_suitability",
            ]
        )
    elif capability_id == "vector.reproject":
        try:
            source_crs = _resolve_crs(input_artifact["spatial"]["crs"])
            source_crs_resolved = True
        except (CRSError, KeyError, TypeError, ValueError, OverflowError):
            source_crs = None
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
        output_metadata = output_artifact.get("metadata", {})
        coordinate_operation = (
            output_metadata.get("coordinate_operation")
            if isinstance(output_metadata, dict)
            else None
        )
        operation_valid = coordinate_operation_evidence_valid(
            coordinate_operation
        )
        if operation_valid:
            operation_accuracy = coordinate_operation.get("accuracy_m")
            operation_area = coordinate_operation.get("area_of_use")
            operation_description = coordinate_operation["description"]
            operation_definition = coordinate_operation.get("definition")
        else:
            operation_accuracy = operation_area = None
            operation_description = operation_definition = None

        area_coverage_status = "not_assessed"
        area_coverage_message = (
            "Operation area-of-use coverage cannot be evaluated without a "
            "geographic input Artifact bbox and reported operation area."
        )
        input_bbox = input_artifact.get("spatial", {}).get("bbox")
        if (
            operation_valid
            and operation_area is not None
            and source_crs_resolved
            and source_crs is not None
            and source_crs.is_geographic
            and input_bbox is not None
        ):
            area_covered = _geographic_bbox_within_area_of_use(
                input_bbox, operation_area
            )
            if area_covered is not None:
                area_coverage_status = "passed" if area_covered else "failed"
                area_coverage_message = (
                    "The input Artifact geographic bbox is fully within "
                    "the selected operation's reported area of use."
                    if area_covered
                    else "The input Artifact geographic bbox extends beyond "
                    "the selected operation's reported area of use."
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
                    "method.coordinate_operation_identity_recorded",
                    "passed" if operation_valid else "failed",
                    (
                        f"Worker reports PROJ selected operation: {operation_description}."
                        if operation_valid
                        else (
                            "The worker omitted or malformed selected "
                            "coordinate-operation evidence."
                        )
                    ),
                    severity="error" if not operation_valid else "info",
                    evidence=evidence,
                ),
                _finding(
                    "method.coordinate_operation_pipeline_recorded",
                    (
                        "passed"
                        if operation_valid and operation_definition is not None
                        else "not_assessed"
                    ),
                    (
                        "The worker recorded the selected PROJ pipeline definition."
                        if operation_definition is not None
                        else "The worker did not expose an exact PROJ pipeline definition."
                    ),
                    severity="info",
                    evidence=evidence,
                ),
                _finding(
                    "method.coordinate_operation_accuracy_reported",
                    (
                        "passed"
                        if operation_valid and operation_accuracy is not None
                        else "not_assessed"
                    ),
                    (
                        f"Worker reports PROJ coordinate-operation accuracy of "
                        f"{operation_accuracy} m."
                        if operation_accuracy is not None
                        else (
                            "PROJ did not report a known accuracy value for "
                            "the selected operation."
                        )
                    ),
                    severity="info",
                    evidence=evidence,
                ),
                _finding(
                    "method.coordinate_operation_area_of_use_reported",
                    (
                        "passed"
                        if operation_valid and operation_area is not None
                        else "not_assessed"
                    ),
                    (
                        f"Worker reports PROJ area of use: {operation_area}."
                        if operation_area is not None
                        else "The selected operation has no reported area-of-use metadata."
                    ),
                    severity="info",
                    evidence=evidence,
                ),
                _finding(
                    "method.input_extent_within_operation_area_of_use",
                    area_coverage_status,
                    area_coverage_message,
                    severity=(
                        "error" if area_coverage_status == "failed" else "warning"
                    ),
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
        if operation_definition is None:
            unassessed.append("exact_coordinate_operation_pipeline")
        if area_coverage_status in {"passed", "failed"}:
            assessed_dimensions.append("coordinate_operation_area_of_use_coverage")
        else:
            unassessed.append("coordinate_operation_area_of_use_coverage")
        unassessed.extend(
            [
                "coordinate_operation_accuracy_suitability",
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
