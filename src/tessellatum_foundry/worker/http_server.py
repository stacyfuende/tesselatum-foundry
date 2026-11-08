"""Authenticated HTTP service for one remotely deployed spatial capability worker.

Terminate TLS at a trusted ingress/proxy and keep this service on a private network.
Each process advertises and executes exactly one capability version.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tessellatum_foundry.capabilities.vector_buffer import buffer_feature_collection
from tessellatum_foundry.capabilities.vector_reproject import reproject_feature_collection

_SUPPORTED_WORKERS = {
    ("vector.buffer", "1.0.0"): "vector-buffer-shapely",
    ("vector.reproject", "1.0.0"): "vector-reproject-pyproj-shapely",
}


def _worker_capability() -> tuple[str, str]:
    return (
        os.environ.get("FOUNDRY_WORKER_CAPABILITY_ID", "vector.buffer"),
        os.environ.get("FOUNDRY_WORKER_CAPABILITY_VERSION", "1.0.0"),
    )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


class WorkerHandler(BaseHTTPRequestHandler):
    server_version = "FoundryRemoteWorker/0.2"

    def _authorized(self) -> bool:
        expected = os.environ.get("FOUNDRY_REMOTE_WORKER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if not expected:
            return False
        return hmac.compare_digest(supplied, f"Bearer {expected}")

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = _json_bytes(payload)
        maximum = int(os.environ.get("FOUNDRY_MAX_OUTPUT_BYTES", str(128 * 1024 * 1024)))
        if len(body) > maximum:
            status = 500
            body = _json_bytes({"error": "worker_response_limit_exceeded"})
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/identity":
            self._send_json(404, {"error": "not_found"})
            return
        capability_id, capability_version = _worker_capability()
        default_implementation = _SUPPORTED_WORKERS.get(
            (capability_id, capability_version), ""
        )
        identity = {
            "worker_id": os.environ.get(
                "FOUNDRY_WORKER_ID", f"remote-{capability_id.replace('.', '-')}-worker"
            ),
            "capability_id": capability_id,
            "capability_version": capability_version,
            "implementation_id": os.environ.get(
                "FOUNDRY_IMPLEMENTATION_ID", default_implementation
            ),
            "implementation_version": os.environ.get(
                "FOUNDRY_IMPLEMENTATION_VERSION", "1.0.0"
            ),
            "runtime_image_digest": os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", ""),
        }
        if (
            (capability_id, capability_version) not in _SUPPORTED_WORKERS
            or not identity["runtime_image_digest"].startswith("sha256:")
        ):
            self._send_json(503, {"error": "worker_identity_not_configured"})
            return
        self._send_json(200, identity)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/execute":
            self._send_json(404, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "content_type_must_be_application_json"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json(411, {"error": "content_length_required"})
            return
        maximum = int(os.environ.get("FOUNDRY_MAX_INPUT_BYTES", str(128 * 1024 * 1024)))
        if content_length < 1 or content_length > maximum:
            self._send_json(413, {"error": "request_size_limit_exceeded"})
            return
        try:
            request = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            if request.get("request_version") != "0.1.0":
                raise ValueError("unsupported request version")
            capability = _worker_capability()
            requested_capability = (
                request.get("capability_id"),
                request.get("capability_version"),
            )
            if requested_capability != capability or capability not in _SUPPORTED_WORKERS:
                self._send_json(400, {"error": "unsupported_capability_version"})
                return
            feature_collection = request["input_feature_collection"]
            parameters = request["parameters"]
            if not isinstance(feature_collection, dict) or not isinstance(parameters, dict):
                raise ValueError("invalid feature collection or parameters")
            if not self.server._execution_slots.acquire(blocking=False):
                self._send_json(
                    503,
                    {"error": "worker_busy"},
                    extra_headers={"Retry-After": "2"},
                )
                return
            try:
                started = time.monotonic()
                if capability == ("vector.buffer", "1.0.0"):
                    result = buffer_feature_collection(
                        feature_collection,
                        input_crs=request["input_crs"],
                        measurement_crs=request["measurement_crs"],
                        **parameters,
                    )
                    output_crs = request["input_crs"]
                elif capability == ("vector.reproject", "1.0.0"):
                    if parameters:
                        raise ValueError("vector.reproject@1.0.0 accepts no extra worker parameters.")
                    result = reproject_feature_collection(
                        feature_collection,
                        input_crs=request["input_crs"],
                        target_crs=request["target_crs"],
                    )
                    output_crs = request["target_crs"]
                else:
                    self._send_json(400, {"error": "unsupported_capability_version"})
                    return
            finally:
                self.server._execution_slots.release()
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            digest = os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", "")
            if not digest.startswith("sha256:"):
                raise RuntimeError("worker image digest is not configured")
            self._send_json(
                200,
                {
                    "feature_collection": result.feature_collection,
                    "crs": output_crs,
                    "duration_ms": duration_ms,
                    "runtime_image_digest": digest,
                },
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid_worker_request"})
        except Exception:
            self._send_json(422, {"error": "capability_execution_failed"})

    def log_message(self, format: str, *args: Any) -> None:
        # Do not log request headers, payloads, or bearer credentials.
        super().log_message(format, *args)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server with a hard cap on active capability executions."""

    request_queue_size = 16
    daemon_threads = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        *,
        max_concurrent_executions: int = 2,
    ):
        if not 1 <= max_concurrent_executions <= 64:
            raise ValueError("max_concurrent_executions must be between 1 and 64.")
        self._execution_slots = threading.BoundedSemaphore(max_concurrent_executions)
        super().__init__(server_address, RequestHandlerClass)


def main() -> None:
    token = os.environ.get("FOUNDRY_REMOTE_WORKER_TOKEN", "")
    digest = os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", "")
    capability = _worker_capability()
    if (
        not token
        or not digest.startswith("sha256:")
        or len(digest) != 71
        or capability not in _SUPPORTED_WORKERS
    ):
        raise SystemExit(
            "Configure the bearer token, full immutable image digest, and a supported "
            "FOUNDRY_WORKER_CAPABILITY_ID/VERSION pair."
        )
    bind = os.environ.get("FOUNDRY_REMOTE_BIND", "0.0.0.0")
    port = int(os.environ.get("FOUNDRY_REMOTE_PORT", "8080"))
    try:
        max_concurrent_executions = int(
            os.environ.get("FOUNDRY_MAX_CONCURRENT_EXECUTIONS", "2")
        )
    except ValueError as error:
        raise SystemExit("FOUNDRY_MAX_CONCURRENT_EXECUTIONS must be an integer.") from error
    server = BoundedThreadingHTTPServer(
        (bind, port),
        WorkerHandler,
        max_concurrent_executions=max_concurrent_executions,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
