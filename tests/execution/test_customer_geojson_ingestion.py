import json

import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.customer_ingestion import (
    CustomerSourceIngestionError,
    ingest_customer_geojson,
)
from tessellatum_foundry.storage import FileSystemArtifactStore


def customer_request():
    return {
        "request_id": "customer-site-001",
        "job_type": "standardize_site_coordinates",
        "product_name": "Nairobi acquisition sites",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
            "coordinate_reference_system": {"authority": "EPSG", "code": 4326},
        },
        "audience": "Property investment team",
        "decision_context": "Metric distance analysis.",
        "geographic_scope": "Nairobi metropolitan region",
    }


def geojson_bytes():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "site-001",
                "properties": {"name": "Westlands"},
                "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
            },
            {
                "type": "Feature",
                "id": "site-002",
                "properties": {"name": "Upper Hill"},
                "geometry": {"type": "Point", "coordinates": [36.8147, -1.3007]},
            },
        ],
    }
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()


def test_ingestion_registers_immutable_artifact_and_input_binding(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    result = ingest_customer_geojson(
        customer_request(),
        geojson_bytes(),
        artifact_store=store,
        capabilities=CapabilityRegistry(),
    )

    assert result["status"] == "source_ingested"
    assert result["feature_count"] == 2
    assert result["artifact"]["media_type"] == (
        "application/vnd.tessellatum.spatial-feature-collection+json"
    )
    assert result["artifact"]["spatial"]["crs"] == {
        "authority": "EPSG",
        "code": 4326,
    }
    binding = result["resolved_input_bindings"]["standardize.features"]
    assert binding["artifact"]["artifact_id"] == result["artifact"]["artifact_id"]
    assert store.read_bytes(result["artifact"]) == geojson_bytes()


def _polygon_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ],
    }


def _outside_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [39.6, -4.0]},
            }
        ],
    }


@pytest.mark.parametrize(
    "content, message",
    [
        (b"not json", "valid UTF-8 GeoJSON"),
        (
            b'{"type":"FeatureCollection","features":[]}',
            "at least one site",
        ),
        (
            json.dumps(_polygon_geojson()).encode(),
            "accepts one point per site",
        ),
        (
            json.dumps(_outside_geojson()).encode(),
            "outside the supported Nairobi intake envelope",
        ),
        (
            b'{"type":"FeatureCollection","crs":{"type":"name"},"features":[]}',
            "Legacy embedded CRS",
        ),
    ],
)
def test_invalid_or_unsupported_geojson_is_rejected(tmp_path, content, message):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    with pytest.raises(CustomerSourceIngestionError, match=message):
        ingest_customer_geojson(
            customer_request(),
            content,
            artifact_store=store,
            capabilities=CapabilityRegistry(),
        )
    metadata = store.root / "metadata"
    assert not list(metadata.rglob("*.json")) if metadata.exists() else True


def test_byte_and_feature_limits_are_enforced(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    with pytest.raises(CustomerSourceIngestionError, match="byte intake limit"):
        ingest_customer_geojson(
            customer_request(),
            geojson_bytes(),
            artifact_store=store,
            capabilities=CapabilityRegistry(),
            max_bytes=10,
        )
    with pytest.raises(CustomerSourceIngestionError, match="feature intake limit"):
        ingest_customer_geojson(
            customer_request(),
            geojson_bytes(),
            artifact_store=store,
            capabilities=CapabilityRegistry(),
            max_features=1,
        )


def test_non_finite_coordinates_are_rejected(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{},"geometry":{"type":"Point","coordinates":[NaN,-1.2]}}]}'
    )
    with pytest.raises(CustomerSourceIngestionError):
        ingest_customer_geojson(
            customer_request(),
            content,
            artifact_store=store,
            capabilities=CapabilityRegistry(),
        )


def test_same_request_reuses_same_immutable_artifact(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first = ingest_customer_geojson(
        customer_request(),
        geojson_bytes(),
        artifact_store=store,
        capabilities=CapabilityRegistry(),
    )
    second = ingest_customer_geojson(
        customer_request(),
        geojson_bytes(),
        artifact_store=store,
        capabilities=CapabilityRegistry(),
    )
    assert second["artifact"]["artifact_id"] == first["artifact"]["artifact_id"]
    assert second["artifact"]["checksum"] == first["artifact"]["checksum"]
