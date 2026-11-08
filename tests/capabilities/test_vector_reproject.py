from __future__ import annotations

import pytest
from pyproj import CRS

from tessellatum_foundry.capabilities.vector_reproject import (
    ReprojectContractError,
    reproject_feature_collection,
)


def point_collection():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "site-01",
            "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
            "properties": {"name": "Nairobi", "kind": "test"},
        }],
    }


def test_reproject_wgs84_to_utm_37s_preserves_feature_identity_and_metadata():
    result = reproject_feature_collection(
        point_collection(),
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs={"authority": "EPSG", "code": 32737},
    )
    feature = result.feature_collection["features"][0]
    x, y = feature["geometry"]["coordinates"]

    assert result.crs.equals(CRS.from_epsg(32737))
    assert x == pytest.approx(260000, abs=15000)
    assert y == pytest.approx(9857000, abs=15000)
    assert feature["id"] == "site-01"
    assert feature["properties"] == {"name": "Nairobi", "kind": "test"}
    assert feature["geometry"]["type"] == "Point"


def test_reproject_uses_xy_axis_order_for_authority_crs():
    collection = point_collection()
    result = reproject_feature_collection(
        collection,
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs={"authority": "EPSG", "code": 3857},
    )
    x, y = result.feature_collection["features"][0]["geometry"]["coordinates"]
    assert x > 4_000_000
    assert y < 0


def test_reproject_preserves_polygon_topology_and_geometry_type():
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "area",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[36.8, -1.3], [36.9, -1.3], [36.9, -1.2],
                                 [36.8, -1.2], [36.8, -1.3]]],
            },
            "properties": {"zone": 3},
        }],
    }
    result = reproject_feature_collection(
        collection,
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs={"authority": "EPSG", "code": 32737},
    )
    feature = result.feature_collection["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"] == {"zone": 3}


@pytest.mark.parametrize("collection", [
    {"type": "FeatureCollection", "features": []},
    {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None}]},
    {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [float("nan"), 1]}
    }]},
    {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2, 3, 4]}
    }]},
])
def test_reproject_rejects_invalid_input_features(collection):
    with pytest.raises(ReprojectContractError):
        reproject_feature_collection(
            collection,
            input_crs={"authority": "EPSG", "code": 4326},
            target_crs={"authority": "EPSG", "code": 32737},
        )


def test_reproject_rejects_unstructured_or_unresolvable_crs():
    with pytest.raises(ReprojectContractError, match="structured"):
        reproject_feature_collection(
            point_collection(),
            input_crs="EPSG:4326",
            target_crs={"authority": "EPSG", "code": 32737},
        )
    with pytest.raises(ReprojectContractError, match="resolvable"):
        reproject_feature_collection(
            point_collection(),
            input_crs={"authority": "EPSG", "code": 99999999},
            target_crs={"authority": "EPSG", "code": 32737},
        )


def test_reproject_rejects_invalid_or_non_finite_transformed_coordinates():
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 100]},
            "properties": {},
        }],
    }
    with pytest.raises(ReprojectContractError):
        reproject_feature_collection(
            collection,
            input_crs={"authority": "EPSG", "code": 4326},
            target_crs={"authority": "EPSG", "code": 3857},
        )


def test_vector_reproject_contract_is_canonical_and_implementation_is_registered():
    from tessellatum_foundry.execution.capabilities import CapabilityRegistry
    from tessellatum_foundry.execution.implementations import ImplementationRegistry
    from tessellatum_foundry.validation.contracts import ContractRegistry

    contracts = ContractRegistry()
    capability_registry = CapabilityRegistry(contracts=contracts)
    capability = capability_registry.get("vector.reproject", "1.0.0")
    assert capability_registry.require_exact(capability) == capability

    implementation_registry = ImplementationRegistry(contracts=contracts)
    manifest = implementation_registry.get("vector-reproject-pyproj-shapely", "1.0.0")
    assert manifest["capability_id"] == "vector.reproject"
    assert manifest["capability_version"] == "1.0.0"
    assert manifest["conformance"]["status"] == "passed"


def test_reproject_preserves_null_properties_and_geometry_collections():
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "mixed",
                "geometry": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {"type": "Point", "coordinates": [36.8, -1.3]},
                        {"type": "LineString", "coordinates": [[36.8, -1.3], [36.9, -1.2]]},
                    ],
                },
                "properties": None,
            }
        ],
    }
    result = reproject_feature_collection(
        collection,
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs={"authority": "EPSG", "code": 32737},
    )
    feature = result.feature_collection["features"][0]
    assert feature["geometry"]["type"] == "GeometryCollection"
    assert feature["properties"] is None
    assert feature["id"] == "mixed"


def test_reproject_preserves_three_dimensional_coordinates():
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [36.8, -1.3, 42.5]},
            "properties": {},
        }],
    }
    result = reproject_feature_collection(
        collection,
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs={"authority": "EPSG", "code": 32737},
    )
    coordinates = result.feature_collection["features"][0]["geometry"]["coordinates"]
    assert len(coordinates) == 3
    assert coordinates[2] == pytest.approx(42.5)
