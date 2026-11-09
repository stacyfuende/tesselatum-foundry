from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tessellatum_foundry import FoundryAPIError, FoundryClient, FoundryTransportError

TOKEN = "foundry-client-test-token-with-at-least-32-characters"
ARTIFACT_BYTES = b'{"type":"FeatureCollection","features":[]}'
ARTIFACT_DIGEST = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, b'{"detail":"unauthorized"}')
            return
        if self.path == "/health":
            self._send(200, b'{"status":"ok"}')
            return
        if self.path == "/v1/artifacts/demo/1.0.0":
            payload = {
                "artifact_id": "demo",
                "version": "1.0.0",
                "size_bytes": len(ARTIFACT_BYTES),
                "checksum": {"algorithm": "sha256", "value": ARTIFACT_DIGEST},
                "storage": {
                    "uri": f"foundry://sha256/{ARTIFACT_DIGEST}",
                    "provider": "foundry-api",
                },
            }
            self._send(200, json.dumps(payload).encode())
            return
        if self.path == "/v1/artifacts/demo/1.0.0/content":
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header("Content-Length", str(len(ARTIFACT_BYTES)))
            self.send_header("X-Content-SHA256", ARTIFACT_DIGEST)
            self.end_headers()
            self.wfile.write(ARTIFACT_BYTES)
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/health")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/v1/reports/missing":
            self._send(404, b'{"detail":"report_not_found"}')
            return
        self._send(404, b'{"detail":"not_found"}')

    def do_POST(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, b'{"detail":"unauthorized"}')
            return
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.server.received_payload = payload
        self._send(
            200,
            json.dumps(
                {
                    "artifact_id": payload["artifact_id"],
                    "version": payload["version"],
                    "content_base64": payload["content_base64"],
                }
            ).encode(),
        )

    def log_message(self, format: str, *args):
        return


@pytest.fixture
def api_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.received_payload = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_requires_secure_url_and_strong_token():
    with pytest.raises(ValueError, match="require HTTPS"):
        FoundryClient("http://api.example.test", bearer_token=TOKEN)
    with pytest.raises(ValueError, match="at least 32"):
        FoundryClient(
            "https://api.example.test",
            bearer_token="short",
        )


def test_client_reads_artifact_and_verifies_immutable_checksum(api_server):
    client = FoundryClient(
        f"http://127.0.0.1:{api_server.server_port}",
        bearer_token=TOKEN,
        allow_insecure_localhost=True,
    )

    assert client.health() == {"status": "ok"}
    metadata = client.get_artifact("demo", "1.0.0")
    assert metadata["checksum"]["value"] == ARTIFACT_DIGEST
    assert client.read_artifact("demo", "1.0.0") == ARTIFACT_BYTES


def test_client_uploads_artifact_as_bounded_base64_json(api_server):
    client = FoundryClient(
        f"http://127.0.0.1:{api_server.server_port}",
        bearer_token=TOKEN,
        allow_insecure_localhost=True,
    )
    response = client.put_artifact(
        artifact_id="upload",
        version="1.0.0",
        content=b"sample",
        created_by="client-test",
        media_type="application/geo+json",
        format_name="GeoJSON",
    )
    assert response["artifact_id"] == "upload"
    assert api_server.received_payload["artifact_id"] == "upload"
    assert api_server.received_payload["content_base64"] == "c2FtcGxl"


def test_client_surfaces_api_errors_and_rejects_redirects(api_server):
    client = FoundryClient(
        f"http://127.0.0.1:{api_server.server_port}",
        bearer_token=TOKEN,
        allow_insecure_localhost=True,
    )
    with pytest.raises(FoundryAPIError) as missing:
        client.get_report("missing")
    assert missing.value.status_code == 404
    assert missing.value.detail == "report_not_found"

    with pytest.raises(FoundryTransportError, match="redirects"):
        client._request("GET", "/redirect")


def test_client_enforces_request_size_limit(api_server):
    client = FoundryClient(
        f"http://127.0.0.1:{api_server.server_port}",
        bearer_token=TOKEN,
        allow_insecure_localhost=True,
        max_request_bytes=8,
    )
    with pytest.raises(FoundryTransportError, match="byte limit"):
        client.put_artifact(
            artifact_id="upload",
            version="1.0.0",
            content=b"too large",
            created_by="client-test",
            media_type="application/geo+json",
            format_name="GeoJSON",
        )

def test_client_uses_longer_timeout_for_recipe_execution():
    class FakeResponse:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size=-1):
            return b'{"status":"succeeded","execution_id":"exec-1"}'

    class RecordingOpener:
        timeout = None

        def open(self, request, timeout):
            self.timeout = timeout
            return FakeResponse()

    client = FoundryClient(
        "https://foundry.example.test",
        bearer_token=TOKEN,
        timeout_seconds=30,
        execution_timeout_seconds=145,
    )
    opener = RecordingOpener()
    client._opener = opener

    result = client.execute_recipe("demo", "1.0.0", actor_id="client-test")

    assert result["status"] == "succeeded"
    assert opener.timeout == 145

