"""Shared semantic validation and normalized request for vector.buffer engines."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


class BufferContractError(ValueError):
    """Raised when a request cannot satisfy the vector.buffer contract."""


_SUPPORTED_INPUT_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}
_LINE_TYPES = {"LineString"}
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


@dataclass(frozen=True)
class ValidatedFeature:
    """A feature after contract checks, with its source geometry preserved."""

    geometry: BaseGeometry
    geometry_json: Mapping[str, Any]
    properties: Mapping[str, Any]
    feature_id: Any | None
    has_id: bool


@dataclass(frozen=True)
class BufferRequest:
    """Engine-neutral normalized request consumed by each buffer implementation."""

    crs: CRS
    epsg_code: int | None
    features: tuple[ValidatedFeature, ...]
    distance: float
    unit: str
    quad_segs: int
    cap_style: str
    join_style: str
    mitre_limit: float
    single_sided: bool


def resolve_crs(value: Any, label: str) -> CRS:
    try:
        if isinstance(value, Mapping):
            if "authority" in value and "code" in value:
                return CRS.from_authority(str(value["authority"]), str(value["code"]))
            return CRS.from_user_input(value)
        return CRS.from_user_input(value)
    except (CRSError, TypeError, ValueError) as error:
        raise BufferContractError(f"{label} is not a resolvable CRS: {error}") from error


def _unit_name(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").split())
    return _UNIT_ALIASES.get(normalized, normalized)


def _validate_crs(input_crs: Any, measurement_crs: Any, unit: str) -> CRS:
    source = resolve_crs(input_crs, "Input CRS")
    measurement = resolve_crs(measurement_crs, "Measurement CRS")
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


def prepare_buffer_request(
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
    require_epsg: bool = False,
) -> BufferRequest:
    """Validate once so all engine implementations receive identical semantics."""
    if not isinstance(distance, (int, float)) or isinstance(distance, bool):
        raise BufferContractError("Distance must be a number.")
    if not math.isfinite(distance) or distance <= 0:
        raise BufferContractError("Distance must be greater than zero.")
    if (
        not isinstance(quad_segs, int)
        or isinstance(quad_segs, bool)
        or not 1 <= quad_segs <= 64
    ):
        raise BufferContractError("quad_segs must be an integer from 1 through 64.")
    if cap_style not in {"round", "flat", "square"}:
        raise BufferContractError("cap_style must be round, flat, or square.")
    if join_style not in {"round", "mitre", "bevel"}:
        raise BufferContractError("join_style must be round, mitre, or bevel.")
    if (
        not isinstance(mitre_limit, (int, float))
        or isinstance(mitre_limit, bool)
        or not math.isfinite(mitre_limit)
        or mitre_limit <= 0
    ):
        raise BufferContractError("mitre_limit must be greater than zero.")
    if not isinstance(unit, str) or not unit.strip():
        raise BufferContractError("unit must be a non-empty string.")
    if not isinstance(single_sided, bool):
        raise BufferContractError("single_sided must be a boolean.")
    if not isinstance(feature_collection, Mapping) or feature_collection.get(
        "type"
    ) != "FeatureCollection":
        raise BufferContractError("Input must be a FeatureCollection.")
    features = feature_collection.get("features")
    if not isinstance(features, list) or not features:
        raise BufferContractError("FeatureCollection must contain at least one feature.")

    resolved_crs = _validate_crs(input_crs, measurement_crs, unit)
    epsg_code = resolved_crs.to_epsg(min_confidence=100)
    if require_epsg and epsg_code is None:
        raise BufferContractError(
            "PostGIS implementation requires a CRS with an unambiguous EPSG identifier."
        )

    validated: list[ValidatedFeature] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise BufferContractError(f"Feature at index {index} must be an object.")
        geometry_json = feature.get("geometry")
        if not isinstance(geometry_json, Mapping):
            raise BufferContractError(
                f"Feature at index {index} must contain a GeoJSON geometry."
            )
        try:
            geometry = shape(geometry_json)
        except (TypeError, ValueError) as error:
            raise BufferContractError(
                f"Feature at index {index} has invalid geometry: {error}"
            ) from error
        if geometry.geom_type not in _SUPPORTED_INPUT_TYPES:
            raise BufferContractError(
                f"Feature at index {index} has unsupported geometry type "
                f"{geometry.geom_type!r}."
            )
        if geometry.is_empty:
            raise BufferContractError(f"Feature at index {index} has empty geometry.")
        if not geometry.is_valid:
            raise BufferContractError(
                f"Feature at index {index} has invalid geometry; "
                "repair it explicitly before buffering."
            )
        if single_sided and geometry.geom_type not in _LINE_TYPES:
            raise BufferContractError(
                "single_sided buffering is supported only for LineString."
            )
        properties = feature.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise BufferContractError(
                f"Feature at index {index} properties must be an object or null."
            )
        validated.append(
            ValidatedFeature(
                geometry=geometry,
                geometry_json=geometry_json,
                properties=dict(properties),
                feature_id=feature.get("id"),
                has_id="id" in feature,
            )
        )

    return BufferRequest(
        crs=resolved_crs,
        epsg_code=epsg_code,
        features=tuple(validated),
        distance=float(distance),
        unit=unit,
        quad_segs=quad_segs,
        cap_style=cap_style,
        join_style=join_style,
        mitre_limit=float(mitre_limit),
        single_sided=single_sided,
    )
