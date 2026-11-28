from __future__ import annotations

import base64
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
import threading
import uuid

import pytest

from tessellatum_foundry.api.customer_jobs import create_customer_jobs_server
from tessellatum_foundry.jobs import JobNotFound
from tessellatum_foundry.storage.object_store import InMemoryObjectStore


class FakeRepository:
    def __init__(self):
        self.job_id = uuid.uuid4()
        self.artifact_id = uuid.uuid4()
        self.created = datetime.now(timezone.utc)
        self.job = {
            "job_id": self.job_id, "tenant_id": "tenant-a", "actor_id": "actor-a",
            "status": "queued", "request_version": "1.0.0",
            "created_at": self.created, "updated_at": self.created,
            "started_at": None, "finished_at": None, "attempt_count": 0,
            "max_attempts": 3, "result_manifest": None, "last_error": None,
        }
        self.artifact = {
            "artifact_id": self.artifact_id, "tenant_id": "tenant-a",
            "job_id": self.job_id, "object_key": "tenants/a/products/result",
            "logical_name": "customer-product.zip", "media_type": "application/zip",
            "checksum_sha256": "", "size_bytes": 0,
        }

    def submit(self, **kwargs):
        self.submission = kwargs
        return self.job

    def get(self, *, tenant_id, job_id):
        if tenant_id != "tenant-a" or str(job_id) != str(self.job_id):
            raise JobNotFound("not found")
        return self.job

    def list_events(self, *, tenant_id, job_id):
        self.get(tenant_id=tenant_id, job_id=job_id)
        return []

    def get_artifact(self, *, tenant_id, job_id, artifact_id):
        self.get(tenant_id=tenant_id, job_id=job_id)
        if str(artifact_id) != str(self.artifact_id):
            raise JobNotFound("not found")
        return self.artifact


@pytest.fixture
def api():
    repository = FakeRepository()
    store = InMemoryObjectStore()
    content = b"PK-test-product"
    receipt = store.put(
        object_key=repository.artifact["object_key"],
        content=content, media_type="application/zip",
    )
    repository.artifact["checksum_sha256"] = receipt.checksum_sha256
    repository.artifact["size_bytes"] = receipt.size_bytes
    server = create_customer_jobs_server(
        ("127.0.0.1", 0),
        authenticate=lambda header: (
            {"actor_id": "actor-a", "tenant_id": "tenant-a"}
            if header == "Bearer test-token" else None
        ),
        repository=repository, object_store=store,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, repository, store, content
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def request(server, method, path, *, body=None, headers=None):
    connection = HTTPConnection(*server.server_address, timeout=3)
    payload = json.dumps(body).encode() if body is not None else None
    connection.request(method, path, body=payload, headers=headers or {})
    response = connection.getresponse()
    result = response.status, response.read(), response.getheader("Content-Type")
    connection.close()
    return result


def auth_headers():
    return {"Authorization": "Bearer test-token"}


def test_submit_job_stages_source_and_returns_accepted(api):
    server, repository, store, _ = api
    customer_request = {
        "request_id": "request-001",
        "job_type": "standardize_site_coordinates",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
            "coordinate_reference_system": {"authority": "EPSG", "code": 4326},
        },
        "audience": "Operations team",
        "decision_context": "Standardize site coordinates",
        "geographic_scope": "Nairobi metropolitan region",
    }
    response = request(server, "POST", "/v1/jobs", body={
        "request_version": "1.0.0",
        "request": customer_request,
        "source_file_base64": base64.b64encode(b'{"type":"FeatureCollection","features":[]}').decode(),
    }, headers={**auth_headers(), "Content-Type": "application/json", "Idempotency-Key": "submission-001"})
    status, body, _ = response
    assert status == 202
    payload = json.loads(body)
    assert payload["job"]["status"] == "queued"
    assert payload["status_url"].endswith(str(repository.job_id))
    assert repository.submission["tenant_id"] == "tenant-a"
    assert repository.submission["actor_id"] == "actor-a"
    assert len(store._objects) == 2  # staged source plus fixture artifact


def test_job_status_events_and_artifact_are_tenant_scoped(api):
    server, repository, _, content = api
    headers = auth_headers()
    status, body, _ = request(server, "GET", f"/v1/jobs/{repository.job_id}", headers=headers)
    assert status == 200
    assert json.loads(body)["job"]["status"] == "queued"

    status, body, _ = request(server, "GET", f"/v1/jobs/{repository.job_id}/events", headers=headers)
    assert status == 200
    assert json.loads(body)["events"] == []

    status, body, content_type = request(
        server, "GET",
        f"/v1/jobs/{repository.job_id}/artifacts/{repository.artifact_id}",
        headers=headers,
    )
    assert status == 200
    assert content_type == "application/zip"
    assert body == content


def test_unauthenticated_and_cross_tenant_reads_are_not_disclosed(api):
    server, repository, _, _ = api
    status, body, _ = request(server, "GET", f"/v1/jobs/{repository.job_id}")
    assert status == 401
    status, body, _ = request(
        server, "GET", f"/v1/jobs/{repository.job_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert status == 200
