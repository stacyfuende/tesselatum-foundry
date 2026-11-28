from __future__ import annotations

import base64
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tessellatum_foundry.api.customer_products import create_customer_product_server


def _post(url, *, token="Bearer customer-token", payload=None, content_type="application/json"):
    body = json.dumps(payload or {}).encode()
    request = Request(
        url,
        data=body,
        headers={"Authorization": token, "Content-Type": content_type},
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
        return {"actor_id": "actor-7", "tenant_id": "tenant-3"} if header == "Bearer customer-token" else None

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
                    "request": {"request_id": "req-123"},
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
