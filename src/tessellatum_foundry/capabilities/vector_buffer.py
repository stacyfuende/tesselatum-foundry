"""Shapely implementation of the engine-independent vector.buffer capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyproj import CRS
from shapely.geometry import mapping

from .buffer_contract import BufferContractError, prepare_buffer_request


@dataclass(frozen=True)
class BufferOutput:
    """Buffered features plus the CRS that applies to their coordinates."""

    feature_collection: dict[str, Any]
    crs: CRS


def buffer_feature_collection(
    feature_collection: dict[str, Any],
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
    """Buffer features without reprojection, repair, or implicit unit conversion.

    Distance uses the projected CRS's native horizontal unit. Feature properties and
    IDs are preserved. Output geometry is Polygon or MultiPolygon. The feature
    payload is GeoJSON-compatible; CRS is separate Foundry metadata, not an RFC 7946
    CRS member.
    """
    request = prepare_buffer_request(
        feature_collection,
        input_crs=input_crs,
        measurement_crs=measurement_crs,
        distance=distance,
        unit=unit,
        quad_segs=quad_segs,
        cap_style=cap_style,
        join_style=join_style,
        mitre_limit=mitre_limit,
        single_sided=single_sided,
    )
    buffered_features: list[dict[str, Any]] = []
    for index, feature in enumerate(request.features):
        result = feature.geometry.buffer(
            request.distance,
            quad_segs=request.quad_segs,
            cap_style=request.cap_style,
            join_style=request.join_style,
            mitre_limit=request.mitre_limit,
            single_sided=request.single_sided,
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
            "properties": dict(feature.properties),
        }
        if feature.has_id:
            output_feature["id"] = feature.feature_id
        buffered_features.append(output_feature)

    return BufferOutput(
        feature_collection={"type": "FeatureCollection", "features": buffered_features},
        crs=request.crs,
    )
