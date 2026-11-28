from __future__ import annotations

from uuid import uuid4

import pytest

from tessellatum_foundry.storage.object_store import InMemoryObjectStore
from tessellatum_foundry.worker.customer_jobs import (
    execute_claimed_customer_job,
    submit_customer_product_job,
)


class FakeRepository:
    def __init__(self):
        self.submission = None
        self.artifact = None
        self.completed = None
        self.atomic_completion = None

    def submit(self, **kwargs):
        self.submission = kwargs
        return {"job_id": str(uuid4()), "status": "queued"}

    def complete_with_artifact(self, **kwargs):
        self.atomic_completion = kwargs
        self.artifact = kwargs["artifact"]
        self.completed = kwargs
        artifact_row = {"artifact_id": uuid4(), **kwargs["artifact"]}
        manifest = {**kwargs["result_manifest"], "artifact_id": str(artifact_row["artifact_id"])}
        return ({"job_id": kwargs["job_id"], "status": "succeeded", "result_manifest": manifest}, artifact_row)


def test_submit_stages_bytes_and_persists_only_checksum_and_object_reference():
    store = InMemoryObjectStore()
    repository = FakeRepository()
    request = {
        "request_id": "site-001",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
        },
    }
    job = submit_customer_product_job(
        repository=repository,
        object_store=store,
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="intake-001",
        request=request,
        source_bytes=b'{"type":"FeatureCollection","features":[]}',
    )
    assert job["status"] == "queued"
    payload = repository.submission["request_payload"]
    assert "source_bytes" not in str(payload)
    assert payload["source"]["checksum_sha256"]
    assert store.get(object_key=payload["source"]["object_key"]).startswith(b"{")
    assert repository.submission["tenant_id"] == "tenant-a"


def test_worker_reuses_product_pipeline_and_publishes_verified_bundle():
    store = InMemoryObjectStore()
    repository = FakeRepository()
    source = b'{"type":"FeatureCollection","features":[]}'
    request = {
        "request_id": "site-002",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
        },
    }
    submit_customer_product_job(
        repository=repository,
        object_store=store,
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="intake-002",
        request=request,
        source_bytes=source,
    )
    job_id = uuid4()
    job = {
        "job_id": job_id,
        "tenant_id": "tenant-a",
        "actor_id": "actor-a",
        "lease_token": uuid4(),
        "request_payload": repository.submission["request_payload"],
    }
    seen = {}

    def runner(received_request, received_source, **kwargs):
        seen["request"] = received_request
        seen["source"] = received_source
        seen["actor_id"] = kwargs["actor_id"]
        return {
            "status": "delivered",
            "delivery": {"content": b"verified-zip-bytes"},
            "acceptance": {"status": "accepted"},
        }

    runtime = {
        "artifact_store": object(),
        "capabilities": object(),
        "recipe_service": object(),
        "cell_templates": {},
        "output_bindings": {},
    }
    result = execute_claimed_customer_job(
        repository=repository,
        object_store=store,
        job=job,
        runtime_resolver=lambda tenant: runtime,
        product_runner=runner,
    )
    assert seen == {"request": request, "source": source, "actor_id": "actor-a"}
    assert result["job"]["status"] == "succeeded"
    assert repository.artifact["format"] == "zip"
    assert repository.atomic_completion["lease_token"] == job["lease_token"]
    assert repository.atomic_completion["artifact"]["checksum_sha256"] == result["manifest"]["checksum_sha256"]
    assert store.get(object_key=result["manifest"]["object_key"]) == b"verified-zip-bytes"
    assert result["manifest"]["checksum_sha256"]


def test_worker_rejects_unaccepted_product_without_publishing_artifact():
    store = InMemoryObjectStore()
    repository = FakeRepository()
    request = {
        "request_id": "site-003",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
        },
    }
    submit_customer_product_job(
        repository=repository,
        object_store=store,
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="intake-003",
        request=request,
        source_bytes=b"{}",
    )
    job = {
        "job_id": uuid4(),
        "tenant_id": "tenant-a",
        "actor_id": "actor-a",
        "lease_token": uuid4(),
        "request_payload": repository.submission["request_payload"],
    }
    runtime = {
        "artifact_store": object(),
        "capabilities": object(),
        "recipe_service": object(),
        "cell_templates": {},
        "output_bindings": {},
    }

    def rejected(*args, **kwargs):
        return {"status": "blocked", "delivery": {"content": None}}

    with pytest.raises(Exception, match="did not pass release acceptance"):
        execute_claimed_customer_job(
            repository=repository,
            object_store=store,
            job=job,
            runtime_resolver=lambda tenant: runtime,
            product_runner=rejected,
        )
    assert repository.artifact is None
    assert repository.completed is None


def test_output_objects_are_content_addressed_across_retry_variants():
    store = InMemoryObjectStore()
    repository = FakeRepository()
    source = b"{}"
    request = {
        "request_id": "site-retry",
        "source_file": {"file_name": "sites.json", "media_type": "application/json"},
    }
    submit_customer_product_job(
        repository=repository,
        object_store=store,
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="retry-intake",
        request=request,
        source_bytes=source,
    )
    job = {
        "job_id": uuid4(),
        "tenant_id": "tenant-a",
        "actor_id": "actor-a",
        "lease_token": uuid4(),
        "request_payload": repository.submission["request_payload"],
    }
    runtime = {
        "artifact_store": object(),
        "capabilities": object(),
        "recipe_service": object(),
        "cell_templates": {},
        "output_bindings": {},
    }
    def runner_with(bundle):
        return lambda *args, **kwargs: {
            "status": "delivered",
            "delivery": {"content": bundle},
            "acceptance": {"status": "accepted"},
        }
    first = execute_claimed_customer_job(
        repository=repository, object_store=store, job=job,
        runtime_resolver=lambda tenant: runtime, product_runner=runner_with(b"zip-A"),
    )
    second = execute_claimed_customer_job(
        repository=repository, object_store=store, job=job,
        runtime_resolver=lambda tenant: runtime, product_runner=runner_with(b"zip-B"),
    )
    assert first["manifest"]["object_key"] != second["manifest"]["object_key"]
    assert store.get(object_key=first["manifest"]["object_key"]) == b"zip-A"
    assert store.get(object_key=second["manifest"]["object_key"]) == b"zip-B"


def test_worker_does_not_return_published_artifact_when_atomic_commit_loses_lease():
    from tessellatum_foundry.jobs import LeaseLost

    store = InMemoryObjectStore()
    repository = FakeRepository()
    request = {
        "request_id": "site-stale",
        "source_file": {"file_name": "sites.json", "media_type": "application/json"},
    }
    submit_customer_product_job(
        repository=repository, object_store=store, tenant_id="tenant-a",
        actor_id="actor-a", idempotency_key="stale-intake",
        request=request, source_bytes=b"{}",
    )
    job = {
        "job_id": uuid4(), "tenant_id": "tenant-a", "actor_id": "actor-a",
        "lease_token": uuid4(), "request_payload": repository.submission["request_payload"],
    }
    runtime = {
        "artifact_store": object(), "capabilities": object(),
        "recipe_service": object(), "cell_templates": {}, "output_bindings": {},
    }
    def stale_completion(**kwargs):
        repository.atomic_completion = kwargs
        raise LeaseLost("lease expired before commit")
    repository.complete_with_artifact = stale_completion

    def runner(*args, **kwargs):
        return {
            "status": "delivered", "delivery": {"content": b"bundle"},
            "acceptance": {"status": "accepted"},
        }
    with pytest.raises(LeaseLost):
        execute_claimed_customer_job(
            repository=repository, object_store=store, job=job,
            runtime_resolver=lambda tenant: runtime, product_runner=runner,
        )
    assert repository.artifact is None
    assert repository.completed is None
    # The object may exist as an orphan, but it is not registered as an artifact.
    assert store.get(object_key=repository.atomic_completion["artifact"]["object_key"]) == b"bundle"
