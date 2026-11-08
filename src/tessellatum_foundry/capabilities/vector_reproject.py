"""Deterministic Shapely implementation of vector.reproject@1.0.0."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely.geometry import mapping, shape
from shapely.ops import transform


class ReprojectContractError(ValueError):
    """Raised when a vector.reproject request violates its semantic contract."""


@dataclass(frozen=True)
class ReprojectOutput:
    """Reprojected FeatureCollection and the CRS describing its coordinates."""

    feature_collection: dict[str, Any]
    crs: CRS


_SUPPORTED_GEOMETRIES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
}


def _resolve_crs(value: Any, label: str) -> CRS:
    try:
        if isinstance(value, Mapping):
            if "authority" in value and "code" in value:
                crs = CRS.from_authority(str(value["authority"]), value["code"])
            elif "wkt2" in value:
                crs = CRS.from_wkt(value["wkt2"])
            else:
                raise ReprojectContractError(
                    f"{label} must declare authority/code or WKT2."
                )
        else:
            raise ReprojectContractError(
                f"{label} must be a structured Foundry CRS declaration."
            )
    except (ProjError, ValueError, TypeError) as error:
        if isinstance(error, ReprojectContractError):
            raise
        raise ReprojectContractError(f"{label} is not a resolvable CRS: {error}") from error
    if not crs.is_bound and not (crs.is_geographic or crs.is_projected or crs.is_geocentric):
        raise ReprojectContractError(f"{label} must be a geographic, projected, or geocentric CRS.")
    return crs


def _coordinates_are_finite(geometry: Any) -> bool:
    if geometry.geom_type == "GeometryCollection":
        return all(_coordinates_are_finite(part) for part in geometry.geoms)
    try:
        stack = [geometry.__geo_interface__["coordinates"]]
        while stack:
            item = stack.pop()
            if isinstance(item, (list, tuple)):
                if item and all(isinstance(value, (int, float)) for value in item):
                    if not all(math.isfinite(value) for value in item):
                        return False
                else:
                    stack.extend(item)
        return True
    except (KeyError, TypeError, ValueError):
        return False


def reproject_feature_collection(
    feature_collection: Mapping[str, Any],
    *,
    input_crs: Any,
    target_crs: Any,
) -> ReprojectOutput:
    """Transform every feature using an explicit source and target CRS.

    Axis order is always x/y regardless of authority axis metadata. Feature IDs,
    properties, geometry types, and coordinate dimensionality are preserved.
    No geometry repair, densification, clipping, or antimeridian splitting occurs.
    """
    if not isinstance(feature_collection, Mapping):
        raise ReprojectContractError("Input must be a GeoJSON FeatureCollection object.")
    if feature_collection.get("type") != "FeatureCollection":
        raise ReprojectContractError("Input type must be FeatureCollection.")
    features = feature_collection.get("features")
    if not isinstance(features, list) or not features:
        raise ReprojectContractError("FeatureCollection must contain at least one feature.")

    source = _resolve_crs(input_crs, "input_crs")
    target = _resolve_crs(target_crs, "target_crs")
    try:
        transformer = Transformer.from_crs(
            source,
            target,
            always_xy=True,
            allow_ballpark=False,
            only_best=True,
        )
    except ProjError as error:
        raise ReprojectContractError(f"No permitted coordinate operation is available: {error}") from error

    output_features: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ReprojectContractError(f"Feature at index {index} is not a GeoJSON Feature.")
        if "geometry" not in feature or not isinstance(feature["geometry"], Mapping):
            raise ReprojectContractError(f"Feature at index {index} has no geometry object.")
        try:
            geometry = shape(feature["geometry"])
        except (AttributeError, TypeError, ValueError) as error:
            raise ReprojectContractError(
                f"Feature at index {index} has unreadable geometry: {error}"
            ) from error
        if geometry.geom_type not in _SUPPORTED_GEOMETRIES:
            raise ReprojectContractError(
                f"Feature at index {index} uses unsupported geometry type {geometry.geom_type!r}."
            )
        if geometry.is_empty or not geometry.is_valid:
            raise ReprojectContractError(
                f"Feature at index {index} geometry must be non-empty and valid."
            )
        if not _coordinates_are_finite(geometry):
            raise ReprojectContractError(
                f"Feature at index {index} contains non-finite coordinates."
            )
        try:
            projected = transform(transformer.transform, geometry)
        except (ProjError, TypeError, ValueError, OverflowError) as error:
            raise ReprojectContractError(
                f"Coordinate transformation failed for feature at index {index}: {error}"
            ) from error
        if (
            projected.is_empty
            or not projected.is_valid
            or projected.geom_type != geometry.geom_type
            or not _coordinates_are_finite(projected)
        ):
            raise ReprojectContractError(
                f"Reprojected geometry at index {index} is invalid, non-finite, or changed type."
            )
        output_feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": mapping(projected),
            "properties": dict(feature.get("properties") or {}),
        }
        if "id" in feature:
            output_feature["id"] = feature["id"]
        output_features.append(output_feature)

    return ReprojectOutput(
        feature_collection={"type": "FeatureCollection", "features": output_features},
        crs=target,
    )
