from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tessellatum_foundry.execution.remote_worker import (
    RemoteVectorBufferWorker,
    RemoteVectorReprojectWorker,
)
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

        remote_worker = RemoteVectorBufferWorker(
            base_url, bearer_token="test-secret", allow_insecure_localhost=True
        )
        assert remote_worker.image_digest() == digest
        remote_result = remote_worker.execute(
            input_bytes=json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "id": "remote-point",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [500000, 1000000]},
                }],
            }).encode(),
            capability_version="1.0.0",
            input_crs={"authority": "EPSG", "code": 32636},
            measurement_crs={"authority": "EPSG", "code": 32636},
            parameters={"distance": 10, "unit": "m"},
            runtime_image_digest=digest,
        )
        assert remote_result.runtime_image_digest == digest
        assert remote_result.feature_collection["features"][0]["geometry"]["type"] in {
            "Polygon", "MultiPolygon"
        }

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


def test_remote_worker_http_service_executes_vector_reproject(monkeypatch):
    digest = "sha256:" + "d" * 64
    monkeypatch.setenv("FOUNDRY_REMOTE_WORKER_TOKEN", "test-secret")
    monkeypatch.setenv("FOUNDRY_WORKER_IMAGE_DIGEST", digest)
    monkeypatch.setenv("FOUNDRY_WORKER_CAPABILITY_ID", "vector.reproject")
    monkeypatch.setenv("FOUNDRY_WORKER_CAPABILITY_VERSION", "1.0.0")
    monkeypatch.setenv(
        "FOUNDRY_IMPLEMENTATION_ID", "vector-reproject-pyproj-shapely"
    )
    monkeypatch.setenv("FOUNDRY_MAX_INPUT_BYTES", "1048576")
    monkeypatch.setenv("FOUNDRY_MAX_OUTPUT_BYTES", "1048576")
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    target_crs = {"authority": "EPSG", "code": 32737}
    try:
        worker = RemoteVectorReprojectWorker(
            base_url,
            bearer_token="test-secret",
            allow_insecure_localhost=True,
        )
        assert worker.image_digest() == digest
        assert worker.implementation_id == "vector-reproject-pyproj-shapely"
        result = worker.execute(
            input_bytes=json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "id": "remote-site",
                    "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
                    "properties": {"name": "Nairobi"},
                }],
            }).encode(),
            capability_version="1.0.0",
            input_crs={"authority": "EPSG", "code": 4326},
            target_crs=target_crs,
            parameters={"target_crs": target_crs},
            runtime_image_digest=digest,
        )
        assert result.runtime_image_digest == digest
        assert result.crs == target_crs
        assert result.coordinate_operation is not None
        assert result.coordinate_operation["description"]
        coordinates = result.feature_collection["features"][0]["geometry"]["coordinates"]
        assert 240000 < coordinates[0] < 280000
        assert 9800000 < coordinates[1] < 9900000
        assert result.feature_collection["features"][0]["properties"] == {
            "name": "Nairobi"
        }

        mismatched_request = Request(
            f"{base_url}/v1/execute",
            data=json.dumps({
                "request_version": "0.1.0",
                "capability_id": "vector.buffer",
                "capability_version": "1.0.0",
                "input_feature_collection": {
                    "type": "FeatureCollection",
                    "features": [],
                },
                "input_crs": {"authority": "EPSG", "code": 4326},
                "measurement_crs": {"authority": "EPSG", "code": 32737},
                "parameters": {"distance": 1, "unit": "metre"},
            }).encode(),
            headers={
                "Authorization": "Bearer test-secret",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urlopen(mismatched_request, timeout=2)
            raise AssertionError("worker accepted a different capability identity")
        except HTTPError as error:
            assert error.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
