from __future__ import annotations

import pytest
from pyproj import CRS

from tessellatum_foundry.capabilities.vector_buffer import (
    BufferContractError,
    buffer_feature_collection,
)


PROJECTED = {"authority": "EPSG", "code": 32737}
POINTS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "p-1",
            "geometry": {"type": "Point", "coordinates": [320000, 9820000]},
            "properties": {"name": "origin"},
        }
    ],
}


def run_buffer(**overrides):
    args = {
        "input_crs": PROJECTED,
        "measurement_crs": PROJECTED,
        "distance": 100,
        "unit": "metre",
    }
    args.update(overrides)
    return buffer_feature_collection(POINTS, **args)


def test_point_buffer_returns_valid_polygon_and_preserves_feature_metadata():
    result = run_buffer()
    feature = result.feature_collection["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"] == {"name": "origin"}
    assert feature["id"] == "p-1"
    assert result.crs.equals(CRS.from_epsg(32737))


def test_buffer_is_deterministic_for_identical_inputs():
    assert run_buffer().feature_collection == run_buffer().feature_collection


@pytest.mark.parametrize(
    ("input_crs", "measurement_crs", "unit", "message"),
    [
        ({"authority": "EPSG", "code": 4326}, PROJECTED, "metre", "must equal"),
        ({"authority": "EPSG", "code": 4326}, {"authority": "EPSG", "code": 4326},
         "degree", "projected"),
        (PROJECTED, PROJECTED, "foot", "must match"),
    ],
)
def test_rejects_incompatible_crs_or_units(input_crs, measurement_crs, unit, message):
    with pytest.raises(BufferContractError, match=message):
        run_buffer(input_crs=input_crs, measurement_crs=measurement_crs, unit=unit)


def test_rejects_invalid_input_geometry_instead_of_repairing_it():
    invalid = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [0, 0], [2, 2], [0, 2], [2, 0], [0, 0]
                ]],
            },
            "properties": {},
        }],
    }
    with pytest.raises(BufferContractError, match="invalid geometry"):
        buffer_feature_collection(
            invalid, input_crs=PROJECTED, measurement_crs=PROJECTED,
            distance=10, unit="metre",
        )


@pytest.mark.parametrize("distance", [0, -1])
def test_rejects_non_positive_distance(distance):
    with pytest.raises(BufferContractError, match="greater than zero"):
        run_buffer(distance=distance)


def test_rejects_unsupported_geometry_type():
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "GeometryCollection", "geometries": []},
            "properties": {},
        }],
    }
    with pytest.raises(BufferContractError, match="unsupported geometry"):
        buffer_feature_collection(
            collection, input_crs=PROJECTED, measurement_crs=PROJECTED,
            distance=10, unit="metre",
        )


def test_supports_explicit_buffer_style_parameters():
    result = run_buffer(quad_segs=4, cap_style="square", join_style="mitre")
    assert result.feature_collection["features"][0]["geometry"]["type"] == "Polygon"
