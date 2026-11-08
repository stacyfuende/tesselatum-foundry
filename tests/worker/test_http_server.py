from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

from tessellatum_foundry.worker.http_server import WorkerHandler
from http.server import ThreadingHTTPServer


def test_remote_worker_http_service_authenticates_and_executes(monkeypatch):
    digest = "sha256:" + "a" * 64
    monkeypatch.setenv("FOUNDRY_REMOTE_WORKER_TOKEN", "test-secret")
    monkeypatch.setenv("FOUNDRY_WORKER_IMAGE_DIGEST", digest)
    monkeypatch.setenv("FOUNDRY_MAX_INPUT_BYTES", "1048576")
    monkeypatch.setenv("FOUNDRY_MAX_OUTPUT_BYTES", "1048576")
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized = Request(f"{base_url}/v1/identity")
        try:
            urlopen(unauthorized, timeout=2)
            raise AssertionError("unauthenticated identity request unexpectedly succeeded")
        except Exception as error:
            assert getattr(error, "code", None) == 401

        identity_request = Request(
            f"{base_url}/v1/identity",
            headers={"Authorization": "Bearer test-secret"},
        )
        with urlopen(identity_request, timeout=2) as response:
            identity = json.loads(response.read())
        assert identity["runtime_image_digest"] == digest
        assert identity["capability_id"] == "vector.buffer"

        payload = {
            "request_version": "0.1.0",
            "capability_id": "vector.buffer",
            "capability_version": "1.0.0",
            "input_feature_collection": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "point-1",
                        "properties": {"source": "test"},
                        "geometry": {"type": "Point", "coordinates": [500000, 1000000]},
                    }
                ],
            },
            "input_crs": {"authority": "EPSG", "code": 32636},
            "measurement_crs": {"authority": "EPSG", "code": 32636},
            "parameters": {"distance": 10, "unit": "m"},
        }
        execute_request = Request(
            f"{base_url}/v1/execute",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": "Bearer test-secret",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(execute_request, timeout=5) as response:
            result = json.loads(response.read())
        assert result["runtime_image_digest"] == digest
        assert result["crs"] == payload["input_crs"]
        assert result["feature_collection"]["features"][0]["geometry"]["type"] in {
            "Polygon",
            "MultiPolygon",
        }
        assert result["duration_ms"] >= 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
