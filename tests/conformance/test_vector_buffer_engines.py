from __future__ import annotations

import math
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from shapely.geometry import shape

from tessellatum_foundry.capabilities.postgis_vector_buffer import (
    buffer_feature_collection_postgis,
)
from tessellatum_foundry.capabilities.vector_buffer import buffer_feature_collection

PROJECTED = {"authority": "EPSG", "code": 32737}
DSN = os.getenv("FOUNDRY_POSTGIS_DSN")


@contextmanager
def _backend(name: str) -> Iterator[Callable]:
    if name == "shapely":
        yield buffer_feature_collection
        return
    if not DSN:
        pytest.skip("FOUNDRY_POSTGIS_DSN is not configured.")
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN) as connection:
        yield lambda data, **kwargs: buffer_feature_collection_postgis(
            connection, data, **kwargs
        )


@pytest.fixture(params=["shapely", "postgis"])
def buffer_engine(request: pytest.FixtureRequest) -> Iterator[Callable]:
    with _backend(request.param) as engine:
        yield engine


def invoke(engine: Callable, data: dict, **overrides):
    parameters = {
        "input_crs": PROJECTED,
        "measurement_crs": PROJECTED,
        "distance": 2,
        "unit": "metre",
    }
    parameters.update(overrides)
    return engine(data, **parameters)


def feature(geometry: dict, *, feature_id="feature-1", properties=None) -> dict:
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": geometry,
        "properties": {"kind": "test"} if properties is None else properties,
    }


def collection(geometry: dict, **kwargs) -> dict:
    return {"type": "FeatureCollection", "features": [feature(geometry, **kwargs)]}


def output_geometry(result):
    return shape(result.feature_collection["features"][0]["geometry"])


def test_point_buffer_has_expected_bounds_area_and_metadata(buffer_engine):
    data = collection(
        {"type": "Point", "coordinates": [320000, 9820000]},
        feature_id="site-7",
        properties={"class": "school"},
    )
    result = invoke(buffer_engine, data, distance=100, quad_segs=8)
    geometry = output_geometry(result)
    expected_area = 2 * 32 * 100**2 * math.sin(math.pi / 32)

    assert geometry.geom_type == "Polygon"
    assert geometry.is_valid
    assert geometry.bounds == pytest.approx((319900, 9819900, 320100, 9820100))
    assert geometry.area == pytest.approx(expected_area, rel=1e-10)
    output_feature = result.feature_collection["features"][0]
    assert output_feature["id"] == "site-7"
    assert output_feature["properties"] == {"class": "school"}
    assert result.crs.to_epsg() == 32737


@pytest.mark.parametrize(
    ("cap_style", "bounds", "area"),
    [
        ("flat", (0, -2, 10, 2), 40),
        ("square", (-2, -2, 12, 2), 56),
    ],
)
def test_line_cap_styles_have_portable_geometry(buffer_engine, cap_style, bounds, area):
    data = collection({
        "type": "LineString",
        "coordinates": [[0, 0], [10, 0]],
    })
    result = invoke(buffer_engine, data, cap_style=cap_style)
    geometry = output_geometry(result)
    assert geometry.is_valid
    assert geometry.bounds == pytest.approx(bounds)
    assert geometry.area == pytest.approx(area)


def test_polygon_buffer_expands_expected_extent(buffer_engine):
    data = collection({
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
    })
    geometry = output_geometry(invoke(buffer_engine, data))
    assert geometry.geom_type == "Polygon"
    assert geometry.bounds == pytest.approx((-2, -2, 12, 12))
    assert geometry.is_valid


def test_multipoint_buffer_produces_multipolygon(buffer_engine):
    data = collection({
        "type": "MultiPoint",
        "coordinates": [[0, 0], [20, 0]],
    })
    geometry = output_geometry(invoke(buffer_engine, data))
    assert geometry.geom_type == "MultiPolygon"
    assert len(geometry.geoms) == 2
    assert geometry.is_valid


def test_single_sided_line_buffer_uses_left_side_and_flat_ends(buffer_engine):
    data = collection({
        "type": "LineString",
        "coordinates": [[0, 0], [10, 0]],
    })
    geometry = output_geometry(
        invoke(buffer_engine, data, single_sided=True, cap_style="round")
    )
    assert geometry.bounds == pytest.approx((0, 0, 10, 2))
    assert geometry.area == pytest.approx(20)


def test_single_sided_rejects_non_line_geometry(buffer_engine):
    data = collection({"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(ValueError, match="only for LineString"):
        invoke(buffer_engine, data, single_sided=True)


def test_shared_contract_rejects_input_crs_mismatch(buffer_engine):
    data = collection({"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(ValueError, match="must equal measurement CRS"):
        invoke(
            buffer_engine,
            data,
            input_crs={"authority": "EPSG", "code": 4326},
        )


def test_shared_contract_rejects_invalid_geometry(buffer_engine):
    data = collection({
        "type": "Polygon",
        "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
    })
    with pytest.raises(ValueError, match="invalid geometry"):
        invoke(buffer_engine, data)


def test_engines_return_topologically_equivalent_geometry():
    if not DSN:
        pytest.skip("FOUNDRY_POSTGIS_DSN is not configured.")
    psycopg = pytest.importorskip("psycopg")
    data = collection({
        "type": "LineString",
        "coordinates": [[0, 0], [10, 0], [10, 10]],
    })
    parameters = {
        "input_crs": PROJECTED,
        "measurement_crs": PROJECTED,
        "distance": 2,
        "unit": "metre",
        "quad_segs": 8,
        "cap_style": "round",
        "join_style": "mitre",
        "mitre_limit": 5,
    }
    shapely_result = buffer_feature_collection(data, **parameters)
    with psycopg.connect(DSN) as connection:
        postgis_result = buffer_feature_collection_postgis(
            connection, data, **parameters
        )
    shapely_geometry = output_geometry(shapely_result)
    postgis_geometry = output_geometry(postgis_result)
    difference = shapely_geometry.symmetric_difference(postgis_geometry)

    assert difference.area <= 1e-7
    assert shapely_geometry.hausdorff_distance(postgis_geometry) <= 1e-8
