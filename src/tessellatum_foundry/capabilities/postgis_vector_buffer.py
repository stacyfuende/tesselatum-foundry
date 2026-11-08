"""PostGIS implementation of the engine-independent vector.buffer capability."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from shapely.geometry import shape

from .buffer_contract import BufferContractError, prepare_buffer_request
from .vector_buffer import BufferOutput


_BUFFER_SQL = """
SELECT
    ST_AsGeoJSON(buffered.geom, 15, 0),
    ST_IsValid(buffered.geom),
    ST_IsEmpty(buffered.geom),
    GeometryType(buffered.geom)
FROM (
    SELECT ST_Buffer(
        ST_SetSRID(ST_GeomFromGeoJSON(%s), %s),
        %s,
        %s
    ) AS geom
) AS buffered
"""


def buffer_feature_collection_postgis(
    connection: Any,
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
    """Execute vector.buffer through a psycopg 3 connection.

    PostGIS receives geometry JSON plus an explicit EPSG SRID. No ST_Transform or
    geography cast is used: distance remains planar in the declared CRS units.
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
        require_epsg=True,
    )
    assert request.epsg_code is not None

    endcap = "flat" if request.single_sided else request.cap_style
    side = "left" if request.single_sided else "both"
    style = (
        f"quad_segs={request.quad_segs} "
        f"endcap={endcap} "
        f"join={request.join_style} "
        f"mitre_limit={request.mitre_limit:.15g} "
        f"side={side}"
    )

    output_features: list[dict[str, Any]] = []
    for index, feature in enumerate(request.features):
        geometry_json = json.dumps(
            feature.geometry_json, allow_nan=False, separators=(",", ":")
        )
        cursor = connection.execute(
            _BUFFER_SQL,
            (geometry_json, request.epsg_code, request.distance, style),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(f"PostGIS returned no buffer result for feature {index}.")
        geometry_text, is_valid, is_empty, geometry_type = row
        if geometry_text is None or is_empty or not is_valid:
            raise BufferContractError(
                f"PostGIS produced an empty or invalid buffer result at feature {index}."
            )
        if geometry_type not in {"POLYGON", "MULTIPOLYGON"}:
            raise BufferContractError(
                f"PostGIS produced unsupported output type {geometry_type!r} "
                f"at feature {index}."
            )
        output_geometry = json.loads(geometry_text)
        parsed_output = shape(output_geometry)
        if parsed_output.is_empty or not parsed_output.is_valid:
            raise BufferContractError(
                f"PostGIS output geometry at feature {index} failed local validation."
            )
        output_feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": output_geometry,
            "properties": dict(feature.properties),
        }
        if feature.has_id:
            output_feature["id"] = feature.feature_id
        output_features.append(output_feature)

    return BufferOutput(
        feature_collection={"type": "FeatureCollection", "features": output_features},
        crs=request.crs,
    )
