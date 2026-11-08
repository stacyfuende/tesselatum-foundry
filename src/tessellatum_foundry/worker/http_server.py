"""Small authenticated HTTP service for a remotely deployed vector.buffer worker.

Terminate TLS at a trusted ingress/proxy and keep this service on a private network.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tessellatum_foundry.capabilities.vector_buffer import buffer_feature_collection


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


class WorkerHandler(BaseHTTPRequestHandler):
    server_version = "FoundryRemoteWorker/0.1"

    def _authorized(self) -> bool:
        expected = os.environ.get("FOUNDRY_REMOTE_WORKER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if not expected:
            return False
        return hmac.compare_digest(supplied, f"Bearer {expected}")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
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
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/identity":
            self._send_json(404, {"error": "not_found"})
            return
        identity = {
            "worker_id": os.environ.get("FOUNDRY_WORKER_ID", "remote-vector-buffer-worker"),
            "capability_id": "vector.buffer",
            "capability_version": "1.0.0",
            "implementation_id": os.environ.get(
                "FOUNDRY_IMPLEMENTATION_ID", "vector-buffer-shapely"
            ),
            "implementation_version": os.environ.get(
                "FOUNDRY_IMPLEMENTATION_VERSION", "1.0.0"
            ),
            "runtime_image_digest": os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", ""),
        }
        if not identity["runtime_image_digest"].startswith("sha256:"):
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
            if request.get("capability_id") != "vector.buffer" or request.get(
                "capability_version"
            ) != "1.0.0":
                raise ValueError("unsupported capability version")
            feature_collection = request["input_feature_collection"]
            parameters = request["parameters"]
            if not isinstance(feature_collection, dict) or not isinstance(parameters, dict):
                raise ValueError("invalid feature collection or parameters")
            started = time.monotonic()
            result = buffer_feature_collection(
                feature_collection,
                input_crs=request["input_crs"],
                measurement_crs=request["measurement_crs"],
                **parameters,
            )
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            digest = os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", "")
            if not digest.startswith("sha256:"):
                raise RuntimeError("worker image digest is not configured")
            self._send_json(
                200,
                {
                    "feature_collection": result.feature_collection,
                    "crs": request["input_crs"],
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


def main() -> None:
    token = os.environ.get("FOUNDRY_REMOTE_WORKER_TOKEN", "")
    digest = os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", "")
    if not token or not digest.startswith("sha256:") or len(digest) != 71:
        raise SystemExit(
            "FOUNDRY_REMOTE_WORKER_TOKEN and a full FOUNDRY_WORKER_IMAGE_DIGEST are required."
        )
    bind = os.environ.get("FOUNDRY_REMOTE_BIND", "0.0.0.0")
    port = int(os.environ.get("FOUNDRY_REMOTE_PORT", "8080"))
    server = ThreadingHTTPServer((bind, port), WorkerHandler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
