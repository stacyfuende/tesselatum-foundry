from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from pyproj import CRS
from pyproj.exceptions import CRSError

from .graph import ValidationFinding

DomainObject = Mapping[str, Any]
ObjectKey = tuple[str, str]


def _object_key(object_id: str, version: str) -> ObjectKey:
    return object_id, version

_GEOGRAPHIC_KINDS = {"geographic", "projected", "geocentric", "engineering", "compound"}
_SPATIAL_DATA_KINDS = {"vector", "raster", "point_cloud", "mesh"}
_SUPPORTED_GEOMETRIES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
    "CircularString",
    "CompoundCurve",
    "CurvePolygon",
    "MultiCurve",
    "MultiSurface",
    "PolyhedralSurface",
    "TIN",
    "Triangle",
    "Unknown",
}
_LINEAR_UNITS = {
    "metre": 1.0,
    "meter": 1.0,
    "metres": 1.0,
    "meters": 1.0,
    "m": 1.0,
    "kilometre": 1000.0,
    "kilometer": 1000.0,
    "km": 1000.0,
    "foot": 0.3048,
    "feet": 0.3048,
    "ft": 0.3048,
    "us survey foot": 1200.0 / 3937.0,
    "us survey feet": 1200.0 / 3937.0,
    "us-ft": 1200.0 / 3937.0,
}


def _crs_from_contract(value: DomainObject) -> CRS:
    if "wkt2" in value:
        return CRS.from_wkt(value["wkt2"])
    authority = value.get("authority")
    code = value.get("code")
    if authority is None or code is None:
        raise CRSError("CRS must contain authority/code or WKT2.")
    return CRS.from_authority(str(authority), str(code))


def _crs_kind(crs: CRS) -> str:
    if crs.is_geographic:
        return "geographic"
    if crs.is_projected:
        return "projected"
    if crs.is_geocentric:
        return "geocentric"
    if crs.is_engineering:
        return "engineering"
    if crs.is_compound:
        return "compound"
    return "unknown"


def _crs_equal(left: CRS, right: CRS) -> bool:
    try:
        return left.equals(right, ignore_axis_order=True)
    except TypeError:
        return left.equals(right)


def _geometry_findings(
    geometry_types: Any,
    *,
    pointer: str,
    required: bool = False,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not geometry_types:
        if required:
            findings.append(
                ValidationFinding(
                    "spatial.geometry_types_missing",
                    "Geometry types are required by the spatial contract but are not declared.",
                    json_pointer=pointer,
                )
            )
        return findings
    for geometry_type in geometry_types:
        if geometry_type not in _SUPPORTED_GEOMETRIES:
            findings.append(
                ValidationFinding(
                    "spatial.geometry_type_unsupported",
                    f"Geometry type {geometry_type!r} is not in Foundry's supported type vocabulary.",
                    json_pointer=pointer,
                )
            )
    return findings


def _validate_bbox(
    bbox: Any,
    *,
    crs: CRS | None,
    pointer: str,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not isinstance(bbox, (list, tuple)) or len(bbox) not in {4, 6}:
        return [
            ValidationFinding(
                "spatial.bbox_invalid_shape",
                "A bounding box must contain 4 values (2D) or 6 values (3D) in GIS x/y order.",
                json_pointer=pointer,
            )
        ]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in bbox):
        return [
            ValidationFinding(
                "spatial.bbox_non_finite",
                "Bounding-box coordinates must all be finite numbers.",
                json_pointer=pointer,
            )
        ]

    if len(bbox) == 4:
        min_x, min_y, max_x, max_y = bbox
        if min_x > max_x or min_y > max_y:
            findings.append(
                ValidationFinding(
                    "spatial.bbox_axis_reversed",
                    "Bounding-box minima must not exceed their corresponding maxima.",
                    json_pointer=pointer,
                )
            )
    else:
        min_x, min_y, min_z, max_x, max_y, max_z = bbox
        if min_x > max_x or min_y > max_y or min_z > max_z:
            findings.append(
                ValidationFinding(
                    "spatial.bbox_axis_reversed",
                    "Bounding-box minima must not exceed their corresponding maxima.",
                    json_pointer=pointer,
                )
            )

    if crs is not None and crs.is_geographic:
        axes = crs.axis_info[:2]
        if len(axes) == 2:
            # Foundry extents use GIS x/y order (east/longitude, north/latitude),
            # independent of authority-defined axis order in the CRS definition.
            x_factor = axes[0].unit_conversion_factor
            y_factor = axes[1].unit_conversion_factor
            if x_factor and y_factor:
                x_limit = math.pi / float(x_factor)
                y_limit = (math.pi / 2) / float(y_factor)
                min_x, min_y = bbox[0], bbox[1]
                max_x, max_y = (bbox[2], bbox[3]) if len(bbox) == 4 else (bbox[3], bbox[4])
                if min_x < -x_limit or max_x > x_limit:
                    findings.append(
                        ValidationFinding(
                            "spatial.bbox_longitude_out_of_range",
                            "The x extent exceeds the longitude domain of its geographic CRS.",
                            json_pointer=pointer,
                        )
                    )
                if min_y < -y_limit or max_y > y_limit:
                    findings.append(
                        ValidationFinding(
                            "spatial.bbox_latitude_out_of_range",
                            "The y extent exceeds the latitude domain of its geographic CRS.",
                            json_pointer=pointer,
                        )
                    )
    return findings


def validate_artifact_spatial_metadata(artifact: DomainObject) -> list[ValidationFinding]:
    """Validate CRS, geometry metadata, and extents on one Artifact version."""
    spatial = artifact.get("spatial")
    if spatial is None:
        return []
    artifact_id = artifact.get("artifact_id", "<unknown>")
    pointer = f"/artifacts/{artifact_id}/spatial"
    findings: list[ValidationFinding] = []
    kind = spatial.get("kind")

    if kind is None:
        return [
            ValidationFinding(
                "spatial.kind_missing",
                "Spatial metadata must identify the artifact's spatial kind.",
                json_pointer=pointer,
            )
        ]

    crs: CRS | None = None
    crs_value = spatial.get("crs")
    if kind in _SPATIAL_DATA_KINDS and crs_value is None:
        findings.append(
            ValidationFinding(
                "spatial.crs_missing",
                f"Spatial kind {kind!r} requires an explicit CRS.",
                json_pointer=f"{pointer}/crs",
            )
        )
    elif crs_value is not None:
        try:
            crs = _crs_from_contract(crs_value)
        except (CRSError, ValueError, TypeError) as error:
            findings.append(
                ValidationFinding(
                    "spatial.crs_invalid",
                    f"CRS cannot be resolved: {error}",
                    json_pointer=f"{pointer}/crs",
                )
            )

    geometry_types = spatial.get("geometry_types")
    if kind == "vector":
        findings.extend(
            _geometry_findings(
                geometry_types,
                pointer=f"{pointer}/geometry_types",
                required=False,
            )
        )
    elif geometry_types:
        findings.append(
            ValidationFinding(
                "spatial.geometry_types_wrong_kind",
                "Geometry types are only valid for vector spatial metadata.",
                json_pointer=f"{pointer}/geometry_types",
            )
        )

    if "bbox" in spatial:
        findings.extend(
            _validate_bbox(spatial["bbox"], crs=crs, pointer=f"{pointer}/bbox")
        )

    if kind == "raster":
        raster = spatial.get("raster")
        if raster is None:
            findings.append(
                ValidationFinding(
                    "spatial.raster_grid_missing",
                    "Raster artifacts must declare grid dimensions.",
                    json_pointer=f"{pointer}/raster",
                )
            )
        elif "resolution" in raster:
            if any(
                not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value == 0
                for value in raster["resolution"]
            ):
                findings.append(
                    ValidationFinding(
                        "spatial.raster_resolution_invalid",
                        "Raster pixel resolutions must be finite and non-zero.",
                        json_pointer=f"{pointer}/raster/resolution",
                    )
                )
    return findings


def _port_map(ports: list[DomainObject]) -> dict[str, DomainObject]:
    return {port["port_id"]: port for port in ports}


def _resolve_input_spatial(
    binding: DomainObject,
    *,
    cells_by_key: Mapping[ObjectKey, DomainObject],
    artifacts: Mapping[ObjectKey, DomainObject],
) -> DomainObject | None:
    if binding["source"] == "artifact":
        reference = binding["artifact"]
        artifact = artifacts.get(_object_key(reference["artifact_id"], reference["version"]))
        return artifact.get("spatial") if artifact is not None else None

    source_key = _object_key(binding["cell_id"], binding["cell_version"])
    source_cell = cells_by_key.get(source_key)
    if source_cell is None:
        return None
    contract = source_cell.get("output_contracts", {}).get(binding["output_port"])
    if contract is None:
        return None
    if "crs" not in contract and "geometry_types" not in contract:
        return None
    return {
        "kind": contract.get("data_kind"),
        "crs": contract.get("crs"),
        "geometry_types": contract.get("geometry_types"),
    }


def _validate_measurement_constraints(
    cell: DomainObject,
    *,
    pointer: str,
) -> list[ValidationFinding]:
    constraints = cell.get("constraints", {})
    measurement_crs_value = constraints.get("measurement_crs")
    linear_unit = constraints.get("linear_unit")
    findings: list[ValidationFinding] = []

    if linear_unit is not None and measurement_crs_value is None:
        return [
            ValidationFinding(
                "spatial.measurement_crs_required",
                "A declared linear measurement unit requires an explicit measurement CRS.",
                json_pointer=f"{pointer}/constraints/measurement_crs",
            )
        ]
    if measurement_crs_value is None:
        return []

    try:
        measurement_crs = _crs_from_contract(measurement_crs_value)
    except (CRSError, ValueError, TypeError) as error:
        return [
            ValidationFinding(
                "spatial.measurement_crs_invalid",
                f"Measurement CRS cannot be resolved: {error}",
                json_pointer=f"{pointer}/constraints/measurement_crs",
            )
        ]

    if not measurement_crs.is_projected:
        findings.append(
            ValidationFinding(
                "spatial.measurement_crs_not_projected",
                "A measurement CRS used for linear planar measurements must be projected.",
                json_pointer=f"{pointer}/constraints/measurement_crs",
            )
        )

    if linear_unit is not None:
        expected_factor = _LINEAR_UNITS.get(str(linear_unit).strip().lower())
        axes = measurement_crs.axis_info[:2]
        if expected_factor is None:
            findings.append(
                ValidationFinding(
                    "spatial.linear_unit_unsupported",
                    f"Linear unit {linear_unit!r} is not in Foundry's supported unit vocabulary.",
                    json_pointer=f"{pointer}/constraints/linear_unit",
                )
            )
        elif len(axes) < 2 or any(axis.unit_conversion_factor is None for axis in axes):
            findings.append(
                ValidationFinding(
                    "spatial.measurement_axis_units_unknown",
                    "The measurement CRS does not expose two known horizontal axis units.",
                    json_pointer=f"{pointer}/constraints/measurement_crs",
                )
            )
        else:
            actual_factors = [float(axis.unit_conversion_factor) for axis in axes]
            if any(
                not math.isclose(factor, expected_factor, rel_tol=1e-9, abs_tol=1e-12)
                for factor in actual_factors
            ):
                actual_units = ", ".join(axis.unit_name for axis in axes)
                findings.append(
                    ValidationFinding(
                        "spatial.linear_unit_mismatch",
                        f"Declared unit {linear_unit!r} does not match measurement CRS axis units "
                        f"({actual_units}).",
                        json_pointer=f"{pointer}/constraints/linear_unit",
                    )
                )
    return findings


def validate_recipe_spatial(
    recipe: DomainObject,
    *,
    cells: Mapping[ObjectKey, DomainObject],
    capabilities: Mapping[ObjectKey, DomainObject],
    artifacts: Mapping[ObjectKey, DomainObject],
) -> list[ValidationFinding]:
    """Validate spatial metadata and capability-specific spatial port constraints."""
    findings: list[ValidationFinding] = []
    cells_by_key = dict(cells)

    for artifact in artifacts.values():
        findings.extend(validate_artifact_spatial_metadata(artifact))

    for node in recipe.get("nodes", []):
        cell_ref = node["cell"]
        cell_key = _object_key(cell_ref["cell_id"], cell_ref["version"])
        cell = cells.get(cell_key)
        if cell is None:
            continue
        pointer = f"/cells/{cell['cell_id']}"
        findings.extend(_validate_measurement_constraints(cell, pointer=pointer))

        capability_ref = cell["capability"]
        capability_key = _object_key(
            capability_ref["capability_id"], capability_ref["version"]
        )
        capability = capabilities.get(capability_key)
        if capability is None:
            continue
        input_ports = _port_map(capability.get("input_ports", []))
        resolved_spatial: dict[str, DomainObject] = {}

        for port_id, binding in cell.get("inputs", {}).items():
            port = input_ports.get(port_id)
            if port is None:
                continue
            spatial = _resolve_input_spatial(
                binding, cells_by_key=cells_by_key, artifacts=artifacts
            )
            if spatial is None:
                if port.get("data_kind") in _SPATIAL_DATA_KINDS or port.get(
                    "spatial", {}
                ).get("crs_required"):
                    findings.append(
                        ValidationFinding(
                            "spatial.input_metadata_missing",
                            f"Spatial metadata for input port {port_id!r} could not be resolved.",
                            json_pointer=f"{pointer}/inputs/{port_id}",
                        )
                    )
                continue
            resolved_spatial[port_id] = spatial
            spatial_constraints = port.get("spatial", {})
            if (
                port.get("data_kind") in _SPATIAL_DATA_KINDS
                and spatial.get("kind") != port.get("data_kind")
            ):
                findings.append(
                    ValidationFinding(
                        "spatial.input_kind_mismatch",
                        f"Input port {port_id!r} expects {port.get('data_kind')!r} "
                        f"spatial data, but received {spatial.get('kind')!r}.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )
            crs_value = spatial.get("crs")
            crs: CRS | None = None
            if crs_value is not None:
                try:
                    crs = _crs_from_contract(crs_value)
                except (CRSError, ValueError, TypeError):
                    # The artifact-level validator emits the detailed invalid-CRS finding.
                    crs = None

            crs_required = spatial_constraints.get(
                "crs_required", port.get("data_kind") in _SPATIAL_DATA_KINDS
            )
            if crs_required and crs is None:
                findings.append(
                    ValidationFinding(
                        "spatial.input_crs_required",
                        f"Input port {port_id!r} requires a resolvable CRS.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )

            measurement_policy = spatial_constraints.get("measurement_crs_policy")
            measurement_crs_value = cell.get("constraints", {}).get("measurement_crs")
            if measurement_policy in {"must_match", "reproject_to_measurement_crs"}:
                if measurement_crs_value is None:
                    findings.append(
                        ValidationFinding(
                            "spatial.measurement_crs_required",
                            f"Input port {port_id!r} declares measurement CRS handling "
                            "but the Geo-Cell has no measurement CRS.",
                            json_pointer=f"{pointer}/constraints/measurement_crs",
                        )
                    )
                elif measurement_policy == "must_match" and crs is not None:
                    try:
                        measurement_crs = _crs_from_contract(measurement_crs_value)
                    except (CRSError, ValueError, TypeError):
                        measurement_crs = None
                    if measurement_crs is not None and not _crs_equal(crs, measurement_crs):
                        findings.append(
                            ValidationFinding(
                                "spatial.input_measurement_crs_mismatch",
                                f"Input port {port_id!r} must already use the Geo-Cell "
                                "measurement CRS; add an explicit CRS transformation.",
                                json_pointer=f"{pointer}/inputs/{port_id}",
                            )
                        )

            expected_crs_type = spatial_constraints.get("crs_type")
            if expected_crs_type and expected_crs_type != "any" and crs is not None:
                actual_crs_type = _crs_kind(crs)
                if actual_crs_type != expected_crs_type:
                    findings.append(
                        ValidationFinding(
                            "spatial.input_crs_type_mismatch",
                            f"Input port {port_id!r} requires a {expected_crs_type} CRS, "
                            f"but received {actual_crs_type}.",
                            json_pointer=f"{pointer}/inputs/{port_id}",
                        )
                    )

            allowed_geometry_types = spatial_constraints.get("geometry_types", [])
            actual_geometry_types = set(spatial.get("geometry_types", []))
            if allowed_geometry_types and not actual_geometry_types.issubset(
                set(allowed_geometry_types)
            ):
                findings.append(
                    ValidationFinding(
                        "spatial.input_geometry_type_mismatch",
                        f"Input port {port_id!r} accepts {sorted(allowed_geometry_types)}, "
                        f"but received {sorted(actual_geometry_types)}.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )
            if allowed_geometry_types and not actual_geometry_types:
                findings.append(
                    ValidationFinding(
                        "spatial.input_geometry_types_missing",
                        f"Input port {port_id!r} requires declared geometry types.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )

        for port_id, port in input_ports.items():
            same_crs_as = port.get("spatial", {}).get("same_crs_as")
            if not same_crs_as or port_id not in resolved_spatial:
                continue
            left_value = resolved_spatial[port_id].get("crs")
            right_spatial = resolved_spatial.get(same_crs_as)
            right_value = right_spatial.get("crs") if right_spatial else None
            if left_value is None or right_value is None:
                findings.append(
                    ValidationFinding(
                        "spatial.same_crs_comparison_unavailable",
                        f"Cannot compare CRS for input ports {port_id!r} and {same_crs_as!r}.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )
                continue
            try:
                left_crs = _crs_from_contract(left_value)
                right_crs = _crs_from_contract(right_value)
            except (CRSError, ValueError, TypeError):
                continue
            if not _crs_equal(left_crs, right_crs):
                findings.append(
                    ValidationFinding(
                        "spatial.input_crs_mismatch",
                        f"Input ports {port_id!r} and {same_crs_as!r} must use equivalent CRSs.",
                        json_pointer=f"{pointer}/inputs/{port_id}",
                    )
                )

        output_ports = _port_map(capability.get("output_ports", []))
        for output_port, contract in cell.get("output_contracts", {}).items():
            output_pointer = f"{pointer}/output_contracts/{output_port}"
            output_port_contract = output_ports.get(output_port, {})
            output_spatial_constraints = output_port_contract.get("spatial", {})
            output_crs = contract.get("crs")
            output_crs_required = (
                contract.get("data_kind") in _SPATIAL_DATA_KINDS
                or output_spatial_constraints.get("crs_required", False)
            )
            if output_crs_required and output_crs is None:
                findings.append(
                    ValidationFinding(
                        "spatial.output_crs_missing",
                        f"Spatial output port {output_port!r} must declare its CRS.",
                        json_pointer=f"{output_pointer}/crs",
                    )
                )
            elif output_crs is not None:
                try:
                    resolved_output_crs = _crs_from_contract(output_crs)
                    expected_output_crs_type = output_spatial_constraints.get("crs_type")
                    if (
                        expected_output_crs_type
                        and expected_output_crs_type != "any"
                        and _crs_kind(resolved_output_crs) != expected_output_crs_type
                    ):
                        findings.append(
                            ValidationFinding(
                                "spatial.output_crs_type_mismatch",
                                f"Output port {output_port!r} requires a "
                                f"{expected_output_crs_type} CRS.",
                                json_pointer=f"{output_pointer}/crs",
                            )
                        )
                except (CRSError, ValueError, TypeError) as error:
                    findings.append(
                        ValidationFinding(
                            "spatial.output_crs_invalid",
                            f"Output CRS cannot be resolved: {error}",
                            json_pointer=f"{output_pointer}/crs",
                        )
                    )
            output_same_crs_as = output_spatial_constraints.get("same_crs_as")
            if output_same_crs_as:
                source_spatial = resolved_spatial.get(output_same_crs_as)
                source_crs_value = source_spatial.get("crs") if source_spatial else None
                if output_crs is not None and source_crs_value is not None:
                    try:
                        if not _crs_equal(
                            _crs_from_contract(output_crs),
                            _crs_from_contract(source_crs_value),
                        ):
                            findings.append(
                                ValidationFinding(
                                    "spatial.output_crs_mismatch",
                                    f"Output port {output_port!r} must use the CRS "
                                    f"of input port {output_same_crs_as!r}.",
                                    json_pointer=f"{output_pointer}/crs",
                                )
                            )
                    except (CRSError, ValueError, TypeError):
                        pass
            allowed_output_geometry_types = set(
                output_spatial_constraints.get("geometry_types", [])
            )
            declared_output_geometry_types = set(contract.get("geometry_types", []))
            if (
                allowed_output_geometry_types
                and (
                    not declared_output_geometry_types
                    or not declared_output_geometry_types.issubset(
                        allowed_output_geometry_types
                    )
                )
            ):
                findings.append(
                    ValidationFinding(
                        "spatial.output_geometry_type_mismatch",
                        f"Output port {output_port!r} permits "
                        f"{sorted(allowed_output_geometry_types)}, but the cell declares "
                        f"{sorted(declared_output_geometry_types)}.",
                        json_pointer=f"{output_pointer}/geometry_types",
                    )
                )
            findings.extend(
                _geometry_findings(
                    contract.get("geometry_types"),
                    pointer=f"{output_pointer}/geometry_types",
                    required=contract.get("data_kind") == "vector",
                )
            )

    return findings
