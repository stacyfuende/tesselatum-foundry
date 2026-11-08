"""PostGIS implementation of the engine-independent vector.buffer capability."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .buffer_contract import (
    BufferContractError,
    BufferOutput,
    prepare_buffer_request,
)


_BUFFER_SQL = """
WITH source AS (
    SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), %s) AS geom
),
checked AS (
    SELECT
        geom,
        ST_IsValid(geom) AS input_is_valid,
        ST_IsEmpty(geom) AS input_is_empty,
        GeometryType(geom) AS input_geometry_type
    FROM source
),
buffered AS (
    SELECT
        CASE
            WHEN input_is_valid AND NOT input_is_empty
            THEN ST_Buffer(geom, %s, %s)
            ELSE NULL::geometry
        END AS geom,
        input_is_valid,
        input_is_empty,
        input_geometry_type
    FROM checked
)
SELECT
    ST_AsGeoJSON(buffered.geom, 15, 0),
    ST_IsValid(buffered.geom),
    ST_IsEmpty(buffered.geom),
    GeometryType(buffered.geom),
    ST_SRID(buffered.geom),
    buffered.input_is_valid,
    buffered.input_is_empty,
    buffered.input_geometry_type
FROM buffered
"""


_POSTGIS_INPUT_TYPES = {
    "Point": "POINT",
    "MultiPoint": "MULTIPOINT",
    "LineString": "LINESTRING",
    "MultiLineString": "MULTILINESTRING",
    "Polygon": "POLYGON",
    "MultiPolygon": "MULTIPOLYGON",
}


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
    """Execute vector.buffer in PostGIS using a psycopg 3 connection.

    PostGIS receives geometry JSON plus an explicit EPSG SRID. No ST_Transform or
    geography cast is used: distance remains planar in the declared CRS units.
    Input validity and output validity are checked by PostGIS itself.
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
        (
            geometry_text,
            is_valid,
            is_empty,
            geometry_type,
            output_srid,
            input_is_valid,
            input_is_empty,
            input_geometry_type,
        ) = row
        if not input_is_valid:
            raise BufferContractError(
                f"PostGIS input geometry at feature {index} is invalid; "
                "repair it explicitly before buffering."
            )
        if input_is_empty:
            raise BufferContractError(f"PostGIS input geometry at feature {index} is empty.")
        if input_geometry_type != _POSTGIS_INPUT_TYPES[feature.geometry_type]:
            raise BufferContractError(
                f"PostGIS input geometry type at feature {index} does not match its declaration."
            )
        if geometry_text is None or is_empty or not is_valid:
            raise BufferContractError(
                f"PostGIS produced an empty or invalid buffer result at feature {index}."
            )
        if output_srid != request.epsg_code:
            raise BufferContractError(
                "PostGIS output SRID does not match the input EPSG SRID."
            )
        if geometry_type not in {"POLYGON", "MULTIPOLYGON"}:
            raise BufferContractError(
                f"PostGIS produced unsupported output type {geometry_type!r} "
                f"at feature {index}."
            )
        output_geometry = json.loads(geometry_text)
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
