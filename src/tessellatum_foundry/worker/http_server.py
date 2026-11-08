"""Authenticated HTTP service for one remotely deployed spatial capability worker.

Terminate TLS at a trusted ingress/proxy and keep this service on a private network.
Each process advertises and executes exactly one capability version.
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

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


class WorkerExecutionTimeout(RuntimeError):
    """Raised when an isolated capability process exceeds its wall-clock limit."""


def _execute_isolated(
    request: dict[str, Any],
    feature_collection: dict[str, Any],
) -> dict[str, Any]:
    try:
        timeout_seconds = int(
            os.environ.get("FOUNDRY_EXECUTION_TIMEOUT_SECONDS", "110")
        )
        max_output_bytes = int(
            os.environ.get("FOUNDRY_MAX_OUTPUT_BYTES", str(128 * 1024 * 1024))
        )
    except ValueError as error:
        raise ValueError("Worker execution and output limits must be integers.") from error
    if not 1 <= timeout_seconds <= 3600 or max_output_bytes < 1:
        raise ValueError("Worker execution and output limits must be positive and in range.")

    cli_request = {
        key: value
        for key, value in request.items()
        if key != "input_feature_collection"
    }
    child_env = os.environ.copy()
    child_env.setdefault("FOUNDRY_MAX_OUTPUT_BYTES", str(max_output_bytes))

    with tempfile.TemporaryDirectory(prefix="foundry-remote-worker-") as directory:
        root = Path(directory)
        request_path = root / "request.json"
        input_path = root / "input.json"
        output_path = root / "output.json"
        request_path.write_bytes(_json_bytes(cli_request))
        input_path.write_bytes(_json_bytes(feature_collection))

        command = [
            sys.executable,
            "-m",
            "tessellatum_foundry.worker.cli",
            "--request",
            str(request_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise WorkerExecutionTimeout(
                f"Capability execution exceeded {timeout_seconds} seconds."
            ) from error

        if completed.returncode != 0:
            raise RuntimeError("Isolated capability process failed.")
        if not output_path.is_file():
            raise RuntimeError("Isolated capability process produced no output.")
        if output_path.stat().st_size > max_output_bytes:
            raise RuntimeError("Isolated capability output exceeded its byte limit.")
        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Isolated capability process returned invalid JSON.") from error
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("feature_collection"), dict)
            or not isinstance(result.get("crs"), dict)
        ):
            raise RuntimeError("Isolated capability process returned an invalid result.")
        return result


class WorkerHandler(BaseHTTPRequestHandler):
    server_version = "FoundryRemoteWorker/0.2"

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
            started = time.monotonic()
            result = _execute_isolated(request, feature_collection)
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            digest = os.environ.get("FOUNDRY_WORKER_IMAGE_DIGEST", "")
            if not digest.startswith("sha256:"):
                raise RuntimeError("worker image digest is not configured")
            self._send_json(
                200,
                {
                    "feature_collection": result["feature_collection"],
                    "crs": result["crs"],
                    "duration_ms": duration_ms,
                    "runtime_image_digest": digest,
                },
            )
        except WorkerExecutionTimeout:
            self._send_json(504, {"error": "worker_execution_timeout"})
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid_worker_request"})
        except Exception:
            self._send_json(422, {"error": "capability_execution_failed"})

    def log_message(self, format: str, *args: Any) -> None:
        # Do not log request headers, payloads, or bearer credentials.
        super().log_message(format, *args)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server with a hard cap on concurrent request handlers."""

    request_queue_size = 16
    daemon_threads = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        *,
        max_concurrent_requests: int = 2,
    ):
        if not 1 <= max_concurrent_requests <= 64:
            raise ValueError("max_concurrent_requests must be between 1 and 64.")
        self._request_slots = threading.BoundedSemaphore(max_concurrent_requests)
        super().__init__(server_address, RequestHandlerClass)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\n"
                    b"Connection: close\r\n"
                    b"Retry-After: 2\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


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
        max_concurrent_requests = int(
            os.environ.get("FOUNDRY_MAX_CONCURRENT_REQUESTS", "2")
        )
    except ValueError as error:
        raise SystemExit("FOUNDRY_MAX_CONCURRENT_REQUESTS must be an integer.") from error
    try:
        execution_timeout = int(
            os.environ.get("FOUNDRY_EXECUTION_TIMEOUT_SECONDS", "110")
        )
    except ValueError as error:
        raise SystemExit("FOUNDRY_EXECUTION_TIMEOUT_SECONDS must be an integer.") from error
    if not 1 <= execution_timeout <= 3600:
        raise SystemExit("FOUNDRY_EXECUTION_TIMEOUT_SECONDS must be between 1 and 3600.")
    server = BoundedThreadingHTTPServer(
        (bind, port),
        WorkerHandler,
        max_concurrent_requests=max_concurrent_requests,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
