"""Authenticated customer-facing HTTP adapter for the spatial product factory.

Mount behind TLS and a trusted ingress. Authentication and tenant-scoped runtime
resolution are injected by the hosting application; this module never accepts
tenant or actor identity from the request body.
"""
from __future__ import annotations

import base64
import binascii
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit


DEFAULT_MAX_SOURCE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 36 * 1024 * 1024


class CustomerAPIError(ValueError):
    """Raised when an authenticated customer submission is invalid."""


def create_customer_product_server(
    address: tuple[str, int],
    *,
    authenticate: Callable[[str], dict[str, str] | None],
    resolve_tenant_runtime: Callable[[str], dict[str, Any]],
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    allowed_origins: set[str] | frozenset[str] = frozenset(),
) -> ThreadingHTTPServer:
    """Create an HTTP server for POST /v1/products.

    authenticate receives the complete Authorization header and must return
    trusted actor_id/tenant_id claims, or None. resolve_tenant_runtime must
    return stores/services isolated to that tenant. Both are hosting concerns;
    no request field can override either identity.
    """
    for name, value in (
        ("max_source_bytes", max_source_bytes),
        ("max_request_bytes", max_request_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")

    normalized_origins = frozenset(allowed_origins)
    for origin in normalized_origins:
        if not isinstance(origin, str):
            raise ValueError("allowed_origins must contain strings.")
        parsed = urlsplit(origin)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"https", "http"}
            or (parsed.scheme != "https" and not local_http)
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin.endswith("/")
        ):
            raise ValueError("allowed_origins must contain exact HTTPS origins (or localhost HTTP origins for development).")

    class Handler(BaseHTTPRequestHandler):
        server_version = "FoundryCustomerAPI/1.0"

        def _send_cors(self) -> None:
            origin = self.headers.get("Origin")
            if origin and origin in normalized_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Expose-Headers", "X-Foundry-Request-ID, Content-Disposition")

        def do_OPTIONS(self) -> None:
            origin = self.headers.get("Origin", "")
            if self.path != "/v1/products":
                self._send_json(404, {"error": "not_found"})
                return
            if origin not in normalized_origins:
                self._send_json(403, {"error": "origin_not_allowed"})
                return
            requested_method = self.headers.get("Access-Control-Request-Method", "")
            requested_headers = {
                value.strip().lower()
                for value in self.headers.get("Access-Control-Request-Headers", "").split(",")
                if value.strip()
            }
            if requested_method != "POST" or not requested_headers.issubset({"authorization", "content-type"}):
                self._send_json(403, {"error": "preflight_not_allowed"})
                return
            self.send_response(204)
            self._send_cors()
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._send_cors()
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/v1/products":
                self._send_json(404, {"error": "not_found"})
                return

            origin = self.headers.get("Origin")
            if origin and origin not in normalized_origins:
                self._send_json(403, {"error": "origin_not_allowed"})
                return

            identity = authenticate(self.headers.get("Authorization", ""))
            if (
                not isinstance(identity, dict)
                or not isinstance(identity.get("actor_id"), str)
                or not identity["actor_id"]
                or not isinstance(identity.get("tenant_id"), str)
                or not identity["tenant_id"]
            ):
                self._send_json(401, {"error": "unauthorized"})
                return

            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "content_type_must_be_application_json"})
                return
            if self.headers.get("Transfer-Encoding"):
                self._send_json(400, {"error": "content_length_required"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send_json(411, {"error": "content_length_required"})
                return
            if content_length < 1 or content_length > max_request_bytes:
                self._send_json(413, {"error": "request_size_limit_exceeded"})
                return

            try:
                payload = json.loads(
                    self.rfile.read(content_length).decode("utf-8"),
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"Invalid JSON constant: {value}")
                    ),
                )
                if not isinstance(payload, dict) or payload.get("request_version") != "1.0.0":
                    raise CustomerAPIError("Unsupported request envelope.")
                request = payload.get("request")
                encoded_source = payload.get("source_file_base64")
                if not isinstance(request, dict) or not isinstance(encoded_source, str):
                    raise CustomerAPIError("Request and source file are required.")
                if set(payload) != {"request_version", "request", "source_file_base64"}:
                    raise CustomerAPIError("Unexpected request envelope fields.")
                try:
                    source_bytes = base64.b64decode(encoded_source, validate=True)
                except (binascii.Error, ValueError) as error:
                    raise CustomerAPIError("Source file encoding is invalid.") from error
                if not source_bytes or len(source_bytes) > max_source_bytes:
                    raise CustomerAPIError("Source file is empty or exceeds the intake limit.")

                from tessellatum_foundry.execution.customer_products import (
                    run_customer_spatial_product,
                )

                runtime = resolve_tenant_runtime(identity["tenant_id"])
                required = {
                    "artifact_store",
                    "capabilities",
                    "recipe_service",
                    "cell_templates",
                    "output_bindings",
                }
                if not isinstance(runtime, dict) or not required.issubset(runtime):
                    raise RuntimeError("Tenant runtime is not fully configured.")
                result = run_customer_spatial_product(
                    request,
                    source_bytes,
                    artifact_store=runtime["artifact_store"],
                    capabilities=runtime["capabilities"],
                    recipe_service=runtime["recipe_service"],
                    cell_templates=runtime["cell_templates"],
                    output_bindings=runtime["output_bindings"],
                    actor_id=identity["actor_id"],
                    policy=runtime.get("policy"),
                    max_source_bytes=max_source_bytes,
                    max_export_bytes=runtime.get("max_export_bytes", 100 * 1024 * 1024),
                    contracts=runtime.get("contracts"),
                )
                delivery = result.get("delivery", {})
                bundle = delivery.get("content")
                if result.get("status") != "delivered" or not isinstance(bundle, bytes):
                    self._send_json(
                        422,
                        {
                            "error": "product_not_releasable",
                            "request_id": result.get("request_id"),
                            "status": result.get("status", "rejected"),
                            "acceptance": result.get("acceptance", {}),
                        },
                    )
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="spatial-product.zip"',
                )
                self.send_header("Content-Length", str(len(bundle)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Foundry-Request-ID", result["request_id"])
                self._send_cors()
                self.end_headers()
                self.wfile.write(bundle)
            except (UnicodeDecodeError, json.JSONDecodeError, CustomerAPIError):
                self._send_json(400, {"error": "invalid_customer_submission"})
            except ValueError:
                self._send_json(422, {"error": "product_request_rejected"})
            except Exception:
                # Do not expose storage paths, worker details, credentials or traces.
                self._send_json(500, {"error": "product_execution_unavailable"})

        def log_message(self, format: str, *args: Any) -> None:
            # Never log authorization headers or customer payloads.
            return

    return ThreadingHTTPServer(address, Handler)
