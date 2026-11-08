from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from tessellatum_foundry.execution.docker_worker import (
    WorkerExecutionError,
    WorkerUnavailableError,
)
from tessellatum_foundry.execution.remote_worker import (
    RemoteVectorBufferWorker,
    RemoteVectorReprojectWorker,
)


class FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1):
        return self.body[:size]


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def identity(digest: str = "sha256:" + "a" * 64) -> dict:
    return {
        "worker_id": "remote-worker-a",
        "capability_id": "vector.buffer",
        "capability_version": "1.0.0",
        "implementation_id": "vector-buffer-shapely",
        "implementation_version": "1.0.0",
        "runtime_image_digest": digest,
    }


def test_remote_worker_requires_https_except_explicit_localhost():
    with pytest.raises(ValueError, match="HTTPS"):
        RemoteVectorBufferWorker("http://worker.example", bearer_token="secret")
    with pytest.raises(ValueError, match="credentials"):
        RemoteVectorBufferWorker("https://user:pass@worker.example", bearer_token="secret")

    worker = RemoteVectorBufferWorker(
        "http://127.0.0.1:8080", bearer_token="secret", allow_insecure_localhost=True
    )
    assert worker.worker_type == "remote"


def test_remote_worker_fetches_identity_and_executes_with_pinned_digest():
    digest = "sha256:" + "a" * 64
    result = {
        "feature_collection": {"type": "FeatureCollection", "features": []},
        "crs": {"authority": "EPSG", "code": 32636},
        "duration_ms": 12,
        "runtime_image_digest": digest,
    }
    worker = RemoteVectorBufferWorker("https://worker.example", bearer_token="secret")
    opener = FakeOpener([FakeResponse(identity(digest)), FakeResponse(result)])
    worker._opener = opener

    assert worker.worker_id == "remote-worker-a"
    assert worker.implementation_id == "vector-buffer-shapely"
    assert worker.image_digest() == digest
    execution = worker.execute(
        input_bytes=b'{"type":"FeatureCollection","features":[]}',
        capability_version="1.0.0",
        input_crs={"authority": "EPSG", "code": 32636},
        measurement_crs={"authority": "EPSG", "code": 32636},
        parameters={"distance": 10},
        runtime_image_digest=digest,
    )

    assert execution.runtime_image_digest == digest
    assert execution.duration_ms == 12
    assert len(opener.requests) == 2
    assert opener.requests[0][0].get_header("Authorization") == "Bearer secret"
    assert opener.requests[1][0].full_url == "https://worker.example/v1/execute"
    assert json.loads(opener.requests[1][0].data)["capability_version"] == "1.0.0"


def test_remote_worker_rejects_identity_for_another_capability():
    other = identity()
    other["capability_id"] = "vector.clip"
    worker = RemoteVectorBufferWorker("https://worker.example", bearer_token="secret")
    worker._opener = FakeOpener([FakeResponse(other)])

    with pytest.raises(WorkerUnavailableError, match="does not support"):
        worker.image_digest()


def test_remote_worker_rejects_runtime_digest_change():
    pinned = "sha256:" + "a" * 64
    changed = "sha256:" + "b" * 64
    worker = RemoteVectorBufferWorker("https://worker.example", bearer_token="secret")
    worker._opener = FakeOpener([FakeResponse(identity(pinned))])

    with pytest.raises(WorkerUnavailableError, match="changed after preflight"):
        worker.execute(
            input_bytes=b'{"type":"FeatureCollection","features":[]}',
            capability_version="1.0.0",
            input_crs={"authority": "EPSG", "code": 32636},
            measurement_crs={"authority": "EPSG", "code": 32636},
            parameters={"distance": 10},
            runtime_image_digest=changed,
        )


def test_remote_worker_rejects_oversized_response():
    worker = RemoteVectorBufferWorker(
        "https://worker.example", bearer_token="secret", max_output_bytes=32
    )
    worker._opener = FakeOpener([FakeResponse(identity())])

    with pytest.raises(WorkerExecutionError, match="response exceeds"):
        worker.image_digest()


def test_remote_worker_does_not_follow_redirects():
    worker = RemoteVectorBufferWorker("https://worker.example", bearer_token="secret")
    redirect = HTTPError("https://worker.example/v1/identity", 302, "Found", {}, None)
    worker._opener = FakeOpener([redirect])

    with pytest.raises(WorkerUnavailableError, match="redirects"):
        worker.image_digest()


def test_remote_reproject_worker_fetches_identity_and_executes_target_crs():
    digest = "sha256:" + "c" * 64
    target_crs = {"authority": "EPSG", "code": 32737}
    result = {
        "feature_collection": {"type": "FeatureCollection", "features": []},
        "crs": target_crs,
        "duration_ms": 8,
        "runtime_image_digest": digest,
        "coordinate_operation": {
            "description": "UTM zone 37S",
            "definition": "+proj=pipeline +step +proj=utm +zone=37 +south",
            "accuracy_m": 0.0,
            "area_of_use": {
                "west": 36.0,
                "south": -80.0,
                "east": 42.0,
                "north": 0.0,
                "name": "UTM zone 37S area",
            },
        },
    }
    identity_payload = {
        "worker_id": "remote-reproject-worker",
        "capability_id": "vector.reproject",
        "capability_version": "1.0.0",
        "implementation_id": "vector-reproject-pyproj-shapely",
        "implementation_version": "1.0.0",
        "runtime_image_digest": digest,
    }
    worker = RemoteVectorReprojectWorker(
        "https://worker.example", bearer_token="secret"
    )
    opener = FakeOpener([FakeResponse(identity_payload), FakeResponse(result)])
    worker._opener = opener

    assert worker.worker_id == "remote-reproject-worker"
    assert worker.implementation_id == "vector-reproject-pyproj-shapely"
    assert worker.image_digest() == digest
    execution = worker.execute(
        input_bytes=b'{"type":"FeatureCollection","features":[]}',
        capability_version="1.0.0",
        input_crs={"authority": "EPSG", "code": 4326},
        target_crs=target_crs,
        parameters={"target_crs": target_crs},
        runtime_image_digest=digest,
    )

    assert execution.runtime_image_digest == digest
    assert execution.crs == target_crs
    assert execution.duration_ms == 8
    assert execution.coordinate_operation["description"] == "UTM zone 37S"
    request_payload = json.loads(opener.requests[1][0].data)
    assert request_payload["capability_id"] == "vector.reproject"
    assert request_payload["target_crs"] == target_crs
    assert request_payload["parameters"] == {}


def test_remote_reproject_worker_rejects_buffer_only_identity():
    worker = RemoteVectorReprojectWorker(
        "https://worker.example", bearer_token="secret"
    )
    worker._opener = FakeOpener([FakeResponse(identity())])

    with pytest.raises(WorkerUnavailableError, match="vector.reproject@1.0.0"):
        worker.image_digest()
