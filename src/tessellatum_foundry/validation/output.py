"""Independent execution-output checks for vector.buffer results."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from dataclasses import dataclass
from typing import Any

from shapely.geometry import shape

from tessellatum_foundry.capabilities.buffer_contract import BufferContractError, resolve_crs


@dataclass(frozen=True)
class OutputFinding:
    code: str
    status: str
    severity: str
    message: str
    json_pointer: str


@dataclass(frozen=True)
class VectorOutputInspection:
    geometry_types: tuple[str, ...]
    findings: tuple[OutputFinding, ...]

    @property
    def passed(self) -> bool:
        return all(finding.status == "passed" for finding in self.findings)


def inspect_vector_buffer_output(
    *,
    input_feature_collection: Mapping[str, Any],
    output_feature_collection: Any,
    input_crs: Any,
    expected_output_crs: Any,
    actual_output_crs: Any,
    permitted_geometry_types: set[str],
) -> VectorOutputInspection:
    """Check output semantics outside the worker process before Artifact commit."""
    findings: list[OutputFinding] = []
    output_types: set[str] = set()

    def add(code: str, passed: bool, message: str, pointer: str) -> None:
        findings.append(
            OutputFinding(
                code=code,
                status="passed" if passed else "failed",
                severity="info" if passed else "error",
                message=message,
                json_pointer=pointer,
            )
        )

    try:
        source_crs = resolve_crs(input_crs, "Input CRS")
        contract_crs = resolve_crs(expected_output_crs, "Expected output CRS")
        result_crs = resolve_crs(actual_output_crs, "Worker output CRS")
        crs_matches = (
            source_crs.equals(contract_crs, ignore_axis_order=True)
            and source_crs.equals(result_crs, ignore_axis_order=True)
        )
    except (BufferContractError, TypeError, ValueError) as error:
        crs_matches = False
        crs_message = f"CRS could not be resolved: {error}"
    else:
        crs_message = "Output CRS equals the input CRS and declared output contract."

    add(
        "output.crs_matches_input",
        crs_matches,
        crs_message,
        "/spatial/crs",
    )

    source_features = input_feature_collection.get("features")
    source_feature_list = source_features if isinstance(source_features, list) else []
    result_features = (
        output_feature_collection.get("features")
        if isinstance(output_feature_collection, Mapping)
        and output_feature_collection.get("type") == "FeatureCollection"
        else None
    )
    valid_collection = (
        isinstance(output_feature_collection, Mapping)
        and output_feature_collection.get("type") == "FeatureCollection"
        and isinstance(result_features, list)
        and len(result_features) > 0
    )
    add(
        "output.feature_collection",
        valid_collection,
        "Output is a non-empty FeatureCollection."
        if valid_collection
        else "Output must be a non-empty FeatureCollection.",
        "/",
    )
    if not valid_collection:
        return VectorOutputInspection((), tuple(findings))

    count_matches = (
        len(source_feature_list) == len(result_features)
        and isinstance(source_features, list)
    )
    add(
        "output.feature_count_preserved",
        count_matches,
        "Output feature count matches input."
        if count_matches
        else "Output feature count differs from input.",
        "/features",
    )

    metadata_matches = count_matches
    geometry_validity = True
    dimensionality_is_2d = True
    coordinates_are_finite = True
    output_types_supported = True
    for index, output_feature in enumerate(result_features):
        if not isinstance(output_feature, Mapping) or output_feature.get("type") != "Feature":
            geometry_validity = False
            metadata_matches = False
            output_types_supported = False
            continue
        geometry_json = output_feature.get("geometry")
        if not isinstance(geometry_json, Mapping):
            geometry_validity = False
            output_types_supported = False
            continue
        try:
            geometry = shape(geometry_json)
        except Exception:
            geometry_validity = False
            output_types_supported = False
            continue
        output_types.add(geometry.geom_type)
        if geometry.is_empty or not geometry.is_valid:
            geometry_validity = False
        if geometry.has_z:
            dimensionality_is_2d = False
        try:
            coordinates = geometry.__geo_interface__["coordinates"]
            stack = [coordinates]
            while stack:
                value = stack.pop()
                if isinstance(value, (list, tuple)):
                    if value and all(isinstance(item, (int, float)) for item in value):
                        coordinates_are_finite = coordinates_are_finite and all(
                            isfinite(item) for item in value
                        )
                    else:
                        stack.extend(value)
        except (KeyError, TypeError, ValueError):
            coordinates_are_finite = False
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            output_types_supported = False
        if geometry.geom_type not in permitted_geometry_types:
            output_types_supported = False
        if index < len(source_feature_list):
            source_feature = source_feature_list[index]
            if not isinstance(source_feature, Mapping):
                metadata_matches = False
                continue
            if output_feature.get("properties") != (source_feature.get("properties") or {}):
                metadata_matches = False
            if ("id" in source_feature) != ("id" in output_feature):
                metadata_matches = False
            elif source_feature.get("id") != output_feature.get("id"):
                metadata_matches = False

    add(
        "output.geometry_validity",
        geometry_validity,
        "All output geometries are non-empty and valid."
        if geometry_validity
        else "At least one output geometry is unreadable, empty, or invalid.",
        "/features",
    )
    add(
        "output.geometry_types",
        output_types_supported and bool(output_types),
        "Output geometry types are within the declared polygonal contract: "
        f"{sorted(output_types)}."
        if output_types_supported and output_types
        else "Output geometry types violate the declared polygonal contract: "
        f"{sorted(output_types)}.",
        "/features",
    )
    add(
        "output.coordinate_finiteness",
        coordinates_are_finite,
        "All output coordinates are finite."
        if coordinates_are_finite
        else "Output contains non-finite or unreadable coordinates.",
        "/features",
    )
    add(
        "output.dimensionality",
        dimensionality_is_2d,
        "Output geometries are two-dimensional."
        if dimensionality_is_2d
        else "Output contains Z coordinates, but vector.buffer declares 2D output.",
        "/features",
    )
    add(
        "output.feature_metadata",
        metadata_matches,
        "Feature IDs and properties are preserved."
        if metadata_matches
        else "Feature count, IDs, or properties differ from input.",
        "/features",
    )
    return VectorOutputInspection(tuple(sorted(output_types)), tuple(findings))
