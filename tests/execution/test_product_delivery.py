"""Tests for verified spatial product export bundles."""

import hashlib
import json
import zipfile
from io import BytesIO

import pytest

from tessellatum_foundry.execution.product_delivery import (
    ProductExportError,
    build_geojson_product_bundle,
)


GEOJSON = json.dumps({
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "properties": {"id": 1}, "geometry": {
        "type": "Point", "coordinates": [36.8, -1.3]
    }}],
}).encode()


class Store:
    def __init__(self, payload=GEOJSON):
        self.payload = payload

    def get_artifact(self, artifact_id, version):
        return {
            "artifact_id": artifact_id,
            "version": version,
            "media_type": "application/geo+json",
            "size_bytes": len(self.payload),
            "checksum": {"algorithm": "sha256", "value": hashlib.sha256(self.payload).hexdigest()},
        }

    def read_bytes(self, artifact, *, max_bytes=None):
        assert artifact["checksum"]["value"] == hashlib.sha256(self.payload).hexdigest()
        if max_bytes is not None and len(self.payload) > max_bytes:
            raise RuntimeError("byte limit exceeded")
        return self.payload


def manifest():
    artifact = Store().get_artifact("zones", "1.0.0")
    return {
        "manifest_version": "1.0.0",
        "product_id": "access-zones",
        "product_version": "1.0.0",
        "status": "accepted",
        "release_allowed": True,
        "acceptance": {"status": "accepted"},
        "outputs": [{
            "output_id": "zones",
            "product_type": "dataset",
            "experience": "Access zones",
            "artifact": artifact,
            "status": "assembled",
        }],
        "provenance": {"execution_id": "run-1"},
    }


def fingerprint(value):
    value = dict(value)
    value.pop("manifest_fingerprint", None)
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def sealed_manifest():
    value = manifest()
    value["manifest_fingerprint"] = fingerprint(value)
    return value


def test_bundle_contains_manifest_index_and_verified_geojson():
    bundle = build_geojson_product_bundle(sealed_manifest(), artifact_store=Store())
    with zipfile.ZipFile(BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {
            "product-manifest.json", "export-index.json", "outputs/zones.geojson"
        }
        index = json.loads(archive.read("export-index.json"))
        payload = archive.read("outputs/zones.geojson")
        assert index["outputs"][0]["checksum"]["value"] == hashlib.sha256(payload).hexdigest()
        assert json.loads(payload)["type"] == "FeatureCollection"


def test_bundle_is_deterministic():
    manifest_value = sealed_manifest()
    first = build_geojson_product_bundle(manifest_value, artifact_store=Store())
    second = build_geojson_product_bundle(manifest_value, artifact_store=Store())
    assert first == second


def test_unaccepted_product_cannot_be_exported():
    value = sealed_manifest()
    value["status"] = "review_required"
    with pytest.raises(ProductExportError, match="Only accepted"):
        build_geojson_product_bundle(value, artifact_store=Store())


def test_manifest_tampering_is_detected():
    value = sealed_manifest()
    value["product_id"] = "tampered"
    with pytest.raises(ProductExportError, match="fingerprint"):
        build_geojson_product_bundle(value, artifact_store=Store())


def test_artifact_metadata_mismatch_is_rejected():
    class WrongStore(Store):
        def get_artifact(self, artifact_id, version):
            value = super().get_artifact(artifact_id, version)
            value["size_bytes"] += 1
            return value

    with pytest.raises(ProductExportError, match="metadata differs"):
        build_geojson_product_bundle(sealed_manifest(), artifact_store=WrongStore())


def test_invalid_geojson_payload_is_rejected():
    class InvalidStore(Store):
        def __init__(self):
            super().__init__(payload=b'{"type":"NotGeoJSON"}')

    value = sealed_manifest()
    artifact = InvalidStore().get_artifact("zones", "1.0.0")
    value["outputs"][0]["artifact"] = artifact
    value["manifest_fingerprint"] = fingerprint(value)
    with pytest.raises(ProductExportError, match="not a GeoJSON"):
        build_geojson_product_bundle(value, artifact_store=InvalidStore())


def test_export_size_limit_is_enforced():
    with pytest.raises(ProductExportError, match="byte limit"):
        build_geojson_product_bundle(sealed_manifest(), artifact_store=Store(), max_output_bytes=1)
