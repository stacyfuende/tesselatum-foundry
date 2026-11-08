from __future__ import annotations

from typing import Any

from tessellatum_foundry.validation.output import inspect_vector_buffer_output

CRS = {"authority": "EPSG", "code": 32737}


def source_collection() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "source-1",
                "geometry": {"type": "Point", "coordinates": [320000, 9820000]},
                "properties": {"class": "building"},
            }
        ],
    }


def output_collection() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "source-1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [319990, 9819990],
                        [320010, 9819990],
                        [320010, 9820010],
                        [319990, 9820010],
                        [319990, 9819990],
                    ]],
                },
                "properties": {"class": "building"},
            }
        ],
    }


def inspect(
    output: Any,
    *,
    actual_crs: Any = CRS,
    source: Any = None,
):
    return inspect_vector_buffer_output(
        input_feature_collection=source if source is not None else source_collection(),
        output_feature_collection=output,
        input_crs=CRS,
        expected_output_crs=CRS,
        actual_output_crs=actual_crs,
        permitted_geometry_types={"Polygon", "MultiPolygon"},
    )


def test_output_critic_accepts_valid_polygonal_result():
    result = inspect(output_collection())

    assert result.passed
    assert result.geometry_types == ("Polygon",)
    assert all(finding.status == "passed" for finding in result.findings)


def test_output_critic_rejects_wrong_crs():
    result = inspect(
        output_collection(),
        actual_crs={"authority": "EPSG", "code": 4326},
    )

    assert not result.passed
    assert any(
        finding.code == "output.crs_matches_input" and finding.status == "failed"
        for finding in result.findings
    )


def test_output_critic_rejects_non_finite_coordinates():
    output = output_collection()
    output["features"][0]["geometry"]["coordinates"][0][1][0] = float("nan")

    result = inspect(output)

    assert not result.passed
    assert any(
        finding.code == "output.coordinate_finiteness" and finding.status == "failed"
        for finding in result.findings
    )


def test_output_critic_reports_malformed_source_feature_list_without_crashing():
    result = inspect(output_collection(), source={"type": "FeatureCollection", "features": None})

    assert not result.passed
    assert any(
        finding.code == "output.feature_count_preserved" and finding.status == "failed"
        for finding in result.findings
    )
