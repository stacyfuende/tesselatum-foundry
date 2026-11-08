from __future__ import annotations

from copy import deepcopy

from tessellatum_foundry.capabilities.vector_reproject import reproject_feature_collection
from tessellatum_foundry.validation.output import inspect_vector_reproject_output


SOURCE_CRS = {"authority": "EPSG", "code": 4326}
TARGET_CRS = {"authority": "EPSG", "code": 32737}
PERMITTED = {
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "GeometryCollection",
}


def source_collection():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "site-01",
                "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
                "properties": {"name": "Nairobi"},
            }
        ],
    }


def inspect(source=None, output=None, actual_crs=TARGET_CRS):
    source = source or source_collection()
    if output is None:
        output = reproject_feature_collection(
            source, input_crs=SOURCE_CRS, target_crs=TARGET_CRS
        ).feature_collection
    return inspect_vector_reproject_output(
        input_feature_collection=source,
        output_feature_collection=output,
        expected_output_crs=TARGET_CRS,
        actual_output_crs=actual_crs,
        permitted_geometry_types=PERMITTED,
    )


def test_reproject_output_critic_accepts_conformant_transformation():
    report = inspect()
    assert report.passed
    assert set(report.geometry_types) == {"Point"}
    assert {finding.code for finding in report.findings} == {
        "output.crs_matches_input",
        "output.feature_collection",
        "output.feature_count_preserved",
        "output.geometry_validity",
        "output.geometry_types",
        "output.coordinate_finiteness",
        "output.dimensionality",
        "output.feature_metadata",
    }


def test_reproject_output_critic_rejects_wrong_crs():
    report = inspect(actual_crs={"authority": "EPSG", "code": 3857})
    finding = next(item for item in report.findings if item.code == "output.crs_matches_input")
    assert finding.status == "failed"


def test_reproject_output_critic_rejects_feature_identity_or_property_changes():
    source = source_collection()
    output = reproject_feature_collection(
        source, input_crs=SOURCE_CRS, target_crs=TARGET_CRS
    ).feature_collection
    changed = deepcopy(output)
    changed["features"][0]["properties"]["name"] = "changed"
    report = inspect(source, changed)
    finding = next(item for item in report.findings if item.code == "output.feature_metadata")
    assert finding.status == "failed"


def test_reproject_output_critic_rejects_geometry_type_changes():
    source = source_collection()
    output = reproject_feature_collection(
        source, input_crs=SOURCE_CRS, target_crs=TARGET_CRS
    ).feature_collection
    changed = deepcopy(output)
    changed["features"][0]["geometry"] = {
        "type": "LineString",
        "coordinates": [[255000, 9856000], [256000, 9857000]],
    }
    report = inspect(source, changed)
    finding = next(item for item in report.findings if item.code == "output.geometry_types")
    assert finding.status == "failed"


def test_reproject_output_critic_rejects_invalid_collection():
    report = inspect(output={"type": "FeatureCollection", "features": []})
    assert not report.passed
    assert any(
        item.code == "output.feature_collection" and item.status == "failed"
        for item in report.findings
    )
