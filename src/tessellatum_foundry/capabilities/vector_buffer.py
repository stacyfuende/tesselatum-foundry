"""Shapely implementation of the engine-independent vector.buffer capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pyproj import CRS
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


class BufferContractError(ValueError):
    """Raised when an input cannot satisfy the vector.buffer contract."""


@dataclass(frozen=True)
class BufferOutput:
    """Buffered features plus the CRS that applies to their coordinates."""

    feature_collection: dict[str, Any]
    crs: CRS


_SUPPORTED_INPUT_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}
_UNIT_ALIASES = {
    "m": "metre",
    "meter": "metre",
    "meters": "metre",
    "metres": "metre",
    "ft": "foot",
    "feet": "foot",
    "foot": "foot",
    "us survey foot": "US survey foot",
}


def _resolve_crs(value: Any, label: str) -> CRS:
    try:
        if isinstance(value, Mapping):
            if "authority" in value and "code" in value:
                return CRS.from_authority(str(value["authority"]), str(value["code"]))
            return CRS.from_user_input(value)
        return CRS.from_user_input(value)
    except (TypeError, ValueError) as error:
        raise BufferContractError(f"{label} is not a resolvable CRS: {error}") from error


def _unit_name(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").split())
    return _UNIT_ALIASES.get(normalized, normalized)


def _validate_measurement_crs(input_crs: Any, measurement_crs: Any, unit: str) -> CRS:
    source = _resolve_crs(input_crs, "Input CRS")
    measurement = _resolve_crs(measurement_crs, "Measurement CRS")
    if not source.equals(measurement):
        raise BufferContractError(
            "Input CRS must equal measurement CRS; reproject explicitly before buffering."
        )
    if not measurement.is_projected:
        raise BufferContractError("Buffer distance requires a projected measurement CRS.")
    axes = measurement.axis_info[:2]
    if len(axes) != 2 or not axes[0].unit_name or not axes[1].unit_name:
        raise BufferContractError("Measurement CRS must expose two horizontal axis units.")
    expected = {_unit_name(axis.unit_name) for axis in axes}
    if len(expected) != 1 or _unit_name(unit) not in expected:
        raise BufferContractError(
            f"Distance unit {unit!r} must match both projected horizontal axis units."
        )
    return measurement


def _feature_geometry(feature: Mapping[str, Any], index: int) -> BaseGeometry:
    if feature.get("type") != "Feature" or not isinstance(feature.get("geometry"), Mapping):
        raise BufferContractError(f"Feature at index {index} must contain a GeoJSON geometry.")
    try:
        geometry = shape(feature["geometry"])
    except (TypeError, ValueError) as error:
        raise BufferContractError(f"Feature at index {index} has invalid geometry: {error}") from error
    if geometry.geom_type not in _SUPPORTED_INPUT_TYPES:
        raise BufferContractError(
            f"Feature at index {index} has unsupported geometry type {geometry.geom_type!r}."
        )
    if geometry.is_empty:
        raise BufferContractError(f"Feature at index {index} has empty geometry.")
    if not geometry.is_valid:
        raise BufferContractError(
            f"Feature at index {index} has invalid geometry; repair it explicitly before buffering."
        )
    return geometry


def buffer_feature_collection(
    feature_collection: Mapping[str, Any],
    *,
    input_crs: Any,
    measurement_crs: Any,
    distance: float,
    unit: str,
    quad_segs: int = 8,
    cap_style: str = "round",
    join_style: str = "round",
    mitre_limit: float = 5.0,
    single_sided: bool = False,
) -> BufferOutput:
    """Buffer each feature without reprojection, repair, or implicit unit conversion.

    Distance is expressed in the native horizontal coordinate unit of the projected
    CRS. Output feature properties and IDs are preserved. Geometry output is always
    Polygon or MultiPolygon.
    """
    if not isinstance(distance, (int, float)) or isinstance(distance, bool):
        raise BufferContractError("Distance must be a number.")
    if distance <= 0:
        raise BufferContractError("Distance must be greater than zero.")
    if not isinstance(quad_segs, int) or isinstance(quad_segs, bool) or not 1 <= quad_segs <= 64:
        raise BufferContractError("quad_segs must be an integer from 1 through 64.")
    if cap_style not in {"round", "flat", "square"}:
        raise BufferContractError("cap_style must be round, flat, or square.")
    if join_style not in {"round", "mitre", "bevel"}:
        raise BufferContractError("join_style must be round, mitre, or bevel.")
    if mitre_limit <= 0:
        raise BufferContractError("mitre_limit must be greater than zero.")
    if not isinstance(single_sided, bool):
        raise BufferContractError("single_sided must be a boolean.")
    if feature_collection.get("type") != "FeatureCollection":
        raise BufferContractError("Input must be a GeoJSON FeatureCollection.")
    features = feature_collection.get("features")
    if not isinstance(features, list) or not features:
        raise BufferContractError("FeatureCollection must contain at least one feature.")

    resolved_crs = _validate_measurement_crs(input_crs, measurement_crs, unit)
    buffered_features: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise BufferContractError(f"Feature at index {index} must be an object.")
        geometry = _feature_geometry(feature, index)
        result = geometry.buffer(
            float(distance),
            quad_segs=quad_segs,
            cap_style=cap_style,
            join_style=join_style,
            mitre_limit=float(mitre_limit),
            single_sided=single_sided,
        )
        if result.is_empty or result.geom_type not in {"Polygon", "MultiPolygon"}:
            raise BufferContractError(
                f"Buffer result at index {index} is empty or has unsupported type "
                f"{result.geom_type!r}."
            )
        if not result.is_valid:
            raise BufferContractError(f"Buffer result at index {index} is not valid.")
        output_feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": mapping(result),
            "properties": dict(feature.get("properties") or {}),
        }
        if "id" in feature:
            output_feature["id"] = feature["id"]
        buffered_features.append(output_feature)

    return BufferOutput(
        feature_collection={"type": "FeatureCollection", "features": buffered_features},
        crs=resolved_crs,
    )
