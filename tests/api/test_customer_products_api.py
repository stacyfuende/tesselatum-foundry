from __future__ import annotations

import base64
import json
import os
import zipfile
from io import BytesIO
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tessellatum_foundry.api.customer_products import create_customer_product_server
from tessellatum_foundry.api.tenant_runtime import LocalTenantRuntimeResolver


def _post(
    url, *, token="Bearer customer-token", payload=None,
    content_type="application/json", origin=None,
):
    body = json.dumps(payload or {}).encode()
    headers = {"Authorization": token, "Content-Type": content_type}
    if origin:
        headers["Origin"] = origin
    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def test_customer_api_authenticates_resolves_tenant_and_returns_product_bundle():
    resolved = []
    def runtime(tenant_id):
        resolved.append(tenant_id)
        return {
            "artifact_store": object(),
            "capabilities": object(),
            "recipe_service": object(),
            "cell_templates": {},
            "output_bindings": {},
        }

    def authenticate(header):
        if header == "Bearer customer-token":
            return {"actor_id": "actor-7", "tenant_id": "tenant-3"}
        return None

    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=authenticate,
        resolve_tenant_runtime=runtime,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import tessellatum_foundry.execution.customer_products as products

        def run(request, source_bytes, **kwargs):
            assert request["request_id"] == "req-123"
            assert request["tenant_id"] == "attacker-selected-tenant"
            assert request["actor_id"] == "attacker-selected-actor"
            assert source_bytes == b'{"type":"FeatureCollection","features":[]}'
            assert kwargs["actor_id"] == "actor-7"
            assert kwargs["artifact_store"] is not None
            return {
                "request_id": request["request_id"],
                "status": "delivered",
                "delivery": {"content": b"PK-test-zip"},
            }

        original = products.run_customer_spatial_product
        products.run_customer_spatial_product = run
        try:
            status, headers, body = _post(
                f"http://127.0.0.1:{server.server_port}/v1/products",
                payload={
                    "request_version": "1.0.0",
                    "request": {
                        "request_id": "req-123",
                        "tenant_id": "attacker-selected-tenant",
                        "actor_id": "attacker-selected-actor",
                    },
                    "source_file_base64": base64.b64encode(
                        b'{"type":"FeatureCollection","features":[]}'
                    ).decode(),
                },
            )
        finally:
            products.run_customer_spatial_product = original

        assert status == 200
        assert headers.get_content_type() == "application/zip"
        assert headers["X-Foundry-Request-ID"] == "req-123"
        assert body == b"PK-test-zip"
        assert resolved == ["tenant-3"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_customer_api_rejects_missing_auth_before_runtime_resolution():
    called = []
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda _: None,
        resolve_tenant_runtime=lambda tenant: called.append(tenant),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _post(
            f"http://127.0.0.1:{server.server_port}/v1/products",
            token="",
            payload={"request_version": "1.0.0"},
        )
        assert status == 401
        assert json.loads(body) == {"error": "unauthorized"}
        assert called == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_customer_api_rejects_invalid_base64_and_never_runs_product(monkeypatch):
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda _: {"actor_id": "actor", "tenant_id": "tenant"},
        resolve_tenant_runtime=lambda _: pytest.fail("runtime must not be resolved"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _post(
            f"http://127.0.0.1:{server.server_port}/v1/products",
            payload={
                "request_version": "1.0.0",
                "request": {"request_id": "req"},
                "source_file_base64": "not base64!",
            },
        )
        assert status == 400
        assert json.loads(body) == {"error": "invalid_customer_submission"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_customer_api_enforces_body_limit_before_reading_payload():
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda _: {"actor_id": "actor", "tenant_id": "tenant"},
        resolve_tenant_runtime=lambda _: pytest.fail("runtime must not be resolved"),
        max_request_bytes=32,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _post(
            f"http://127.0.0.1:{server.server_port}/v1/products",
            payload={"large": "x" * 100},
        )
        assert status == 413
        assert json.loads(body) == {"error": "request_size_limit_exceeded"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_customer_api_rejects_unknown_routes():
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda _: None,
        resolve_tenant_runtime=lambda _: {},
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _post(f"http://127.0.0.1:{server.server_port}/wrong")
        assert status == 404
        assert json.loads(body) == {"error": "not_found"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

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



def test_customer_api_cors_allows_only_exact_configured_origin_and_preflight():
    allowed = "https://customer.example"
    server = create_customer_product_server(
        ("127.0.0.1", 0),
        authenticate=lambda _: None,
        resolve_tenant_runtime=lambda _: {},
        allowed_origins={allowed},
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1/products"
        preflight = Request(
            url,
            headers={
                "Origin": allowed,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            method="OPTIONS",
        )
        with urlopen(preflight, timeout=3) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == allowed
            assert response.headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"
            assert response.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"

        denied = Request(
            url,
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            method="OPTIONS",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(denied, timeout=3)
        assert error.value.code == 403
        assert json.loads(error.value.read()) == {"error": "origin_not_allowed"}

        status, headers, body = _post(url, origin="https://attacker.example")
        assert status == 403
        assert json.loads(body) == {"error": "origin_not_allowed"}
        assert "Access-Control-Allow-Origin" not in headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_customer_api_rejects_insecure_non_local_cors_origins():
    with pytest.raises(ValueError, match="exact HTTPS origins"):
        create_customer_product_server(
            ("127.0.0.1", 0),
            authenticate=lambda _: None,
            resolve_tenant_runtime=lambda _: {},
            allowed_origins={"http://customer.example"},
        )
