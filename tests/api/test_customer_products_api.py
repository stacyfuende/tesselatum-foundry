from __future__ import annotations

import base64
import json
import os
import threading
import zipfile
from io import BytesIO

import pytest

from tessellatum_foundry.api.customer_products import create_customer_product_server
from tessellatum_foundry.api.tenant_runtime import LocalTenantRuntimeResolver


@pytest.mark.skipif(
    not os.getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="Docker-backed product integration requires the CI worker image",
)
def test_authenticated_http_submission_runs_tenant_product_and_returns_verified_bundle(
    tmp_path,
):
    source = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "site-001",
                "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
                "properties": {"site_name": "Central acquisition site", "use": "mixed"},
            }
        ],
    }
    source_bytes = json.dumps(source, separators=(",", ":")).encode("utf-8")
    customer_request = {
        "request_id": "http-site-001",
        "job_type": "standardize_site_coordinates",
        "product_name": "Nairobi acquisition sites",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
            "coordinate_reference_system": {"authority": "EPSG", "code": 4326},
        },
        "audience": "Property investment team",
        "decision_context": "Prepare acquisition candidates for metric distance analysis.",
        "geographic_scope": "Nairobi metropolitan region",
    }
    resolver = LocalTenantRuntimeResolver(tmp_path / "tenants")
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda header: (
            {"actor_id": "integration-actor", "tenant_id": "trusted-tenant"}
            if header == "Bearer integration-token"
            else None
        ),
        resolve_tenant_runtime=resolver,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from urllib.request import Request, urlopen

        payload = {
            "request_version": "1.0.0",
            "request": customer_request,
            "source_file_base64": base64.b64encode(source_bytes).decode("ascii"),
        }
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/products",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer integration-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            bundle_bytes = response.read()
            assert response.status == 200
            assert response.headers.get_content_type() == "application/zip"
            assert response.headers["X-Foundry-Request-ID"] == "http-site-001"

        with zipfile.ZipFile(BytesIO(bundle_bytes)) as bundle:
            names = set(bundle.namelist())
            assert {
                "product-manifest.json",
                "manifest-fingerprint-input.json",
                "export-index.json",
                "outputs/standardized-sites.geojson",
            }.issubset(names)
            manifest = json.loads(bundle.read("product-manifest.json"))
            output = json.loads(bundle.read("outputs/standardized-sites.geojson"))

        assert manifest["acceptance"]["status"] == "accepted"
        assert manifest["acceptance"]["release_allowed"] is True
        assert manifest["product"]["title"] == "Nairobi acquisition sites"
        feature = output["features"][0]
        assert feature["id"] == "site-001"
        assert feature["properties"] == {
            "site_name": "Central acquisition site",
            "use": "mixed",
        }
        east, north = feature["geometry"]["coordinates"][:2]
        assert 200_000 < east < 400_000
        assert 9_800_000 < north < 9_900_000

        tenant_runtime = resolver("trusted-tenant")
        other_runtime = resolver("different-tenant")
        assert tenant_runtime["artifact_store"] is not other_runtime["artifact_store"]
        assert tenant_runtime["recipe_service"] is not other_runtime["recipe_service"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
