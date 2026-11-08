"""Independent execution-output checks for vector.buffer results."""

from __future__ import annotations

from collections.abc import Mapping
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
        isinstance(source_features, list) and len(source_features) == len(result_features)
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
        except (AttributeError, TypeError, ValueError):
            geometry_validity = False
            output_types_supported = False
            continue
        output_types.add(geometry.geom_type)
        if geometry.is_empty or not geometry.is_valid:
            geometry_validity = False
        if geometry.has_z:
            dimensionality_is_2d = False
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            output_types_supported = False
        if geometry.geom_type not in permitted_geometry_types:
            output_types_supported = False
        if index < len(source_features):
            source_feature = source_features[index]
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
