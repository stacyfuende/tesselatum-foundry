from __future__ import annotations

import os
import uuid

import pytest

from tessellatum_foundry.jobs import (
    IdempotencyConflict,
    JobNotFound,
    LeaseLost,
    PostgresJobRepository,
    canonical_request_sha256,
)


def test_canonical_request_hash_ignores_object_key_order():
    first = {"product": "site-screen", "source": {"sha256": "a" * 64}, "options": {"b": 2, "a": 1}}
    second = {"options": {"a": 1, "b": 2}, "source": {"sha256": "a" * 64}, "product": "site-screen"}
    assert canonical_request_sha256("1", first) == canonical_request_sha256("1", second)


def test_canonical_request_hash_changes_with_semantic_version_or_payload():
    payload = {"product": "site-screen"}
    assert canonical_request_sha256("1", payload) != canonical_request_sha256("2", payload)
    assert canonical_request_sha256("1", payload) != canonical_request_sha256(
        "1", {"product": "route"}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "Bearer secret"},
        {"nested": {"api_key": "secret"}},
        {"source_bytes": "YmFzZTY0"},
        {"not_finite": float("nan")},
    ],
)
def test_request_hash_rejects_secrets_and_non_finite_values(payload):
    with pytest.raises(ValueError):
        canonical_request_sha256("1", payload)


@pytest.fixture
def postgres_repository():
    dsn = os.environ.get("FOUNDRY_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set FOUNDRY_TEST_POSTGRES_DSN to run isolated Postgres repository tests.")
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row

    schema = "foundry"
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        exists = conn.execute(
            "select exists (select 1 from information_schema.schemata where schema_name = %s)",
            (schema,),
        ).fetchone()["exists"]
        if exists:
            pytest.skip("Refusing to overwrite an existing foundry schema in the test database.")
        conn.execute("create schema foundry")
        conn.execute(
            """
            create table foundry.jobs (
                job_id uuid primary key default gen_random_uuid(),
                tenant_id text not null,
                actor_id text not null,
                idempotency_key text not null,
                request_version text not null,
                request_sha256 text not null,
                request_payload jsonb not null,
                status text not null default 'queued',
                attempt_count integer not null default 0,
                max_attempts integer not null default 3,
                available_at timestamptz not null default now(),
                lease_token uuid,
                lease_expires_at timestamptz,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(),
                started_at timestamptz,
                finished_at timestamptz,
                last_error jsonb,
                result_manifest jsonb,
                unique (tenant_id, idempotency_key)
            )
            """
        )
        conn.execute(
            """
            create table foundry.job_events (
                event_id bigint generated always as identity primary key,
                tenant_id text not null,
                job_id uuid not null references foundry.jobs(job_id),
                event_type text not null,
                from_status text,
                to_status text,
                detail jsonb not null default '{}'::jsonb,
                occurred_at timestamptz not null default now()
            )
            """
        )
        conn.execute(
            """
            create table foundry.artifacts (
                artifact_id uuid primary key default gen_random_uuid(),
                tenant_id text not null,
                job_id uuid not null references foundry.jobs(job_id),
                artifact_kind text not null,
                logical_name text not null,
                object_key text not null,
                media_type text not null,
                format text,
                checksum_sha256 text not null,
                size_bytes bigint not null,
                metadata jsonb not null default '{}'::jsonb,
                created_at timestamptz not null default now(),
                expires_at timestamptz,
                unique (tenant_id, object_key)
            )
            """
        )
    try:
        yield PostgresJobRepository(dsn=dsn)
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute("drop schema if exists foundry cascade")


def test_postgres_submit_idempotency_and_tenant_scoping(postgres_repository):
    repo = postgres_repository
    payload = {"product": "site-screen", "source_sha256": "a" * 64}
    created = repo.submit(
        tenant_id="tenant-a", actor_id="actor-a", idempotency_key="request-1",
        request_version="1", request_payload=payload,
    )
    replay = repo.submit(
        tenant_id="tenant-a", actor_id="actor-a", idempotency_key="request-1",
        request_version="1", request_payload=payload,
    )
    assert replay["job_id"] == created["job_id"]
    assert len(repo.list_events(tenant_id="tenant-a", job_id=created["job_id"])) == 1
    with pytest.raises(IdempotencyConflict):
        repo.submit(
            tenant_id="tenant-a", actor_id="actor-a", idempotency_key="request-1",
            request_version="1", request_payload={"product": "different"},
        )
    with pytest.raises(JobNotFound):
        repo.get(tenant_id="tenant-b", job_id=created["job_id"])


def test_postgres_claim_complete_and_stale_lease_fencing(postgres_repository):
    repo = postgres_repository
    job = repo.submit(
        tenant_id="tenant-a", actor_id="actor-a", idempotency_key="request-2",
        request_version="1", request_payload={"product": "route"},
    )
    claimed = repo.claim_next(worker_id="worker-a")
    assert claimed["job_id"] == job["job_id"]
    assert claimed["status"] == "running"
    repo.complete(
        tenant_id="tenant-a", job_id=job["job_id"], lease_token=claimed["lease_token"],
        result_manifest={"artifact_count": 0},
    )
    with pytest.raises(LeaseLost):
        repo.complete(
            tenant_id="tenant-a", job_id=job["job_id"], lease_token=uuid.uuid4(),
            result_manifest={},
        )
    assert repo.get(tenant_id="tenant-a", job_id=job["job_id"])["status"] == "succeeded"


def test_postgres_atomic_artifact_completion_rolls_back_on_stale_lease(postgres_repository):
    repo = postgres_repository
    job = repo.submit(
        tenant_id="tenant-atomic", actor_id="actor", idempotency_key="atomic",
        request_version="1", request_payload={"product": "zip"},
    )
    claimed = repo.claim_next(worker_id="worker")
    artifact = {
        "artifact_kind": "customer_product_bundle",
        "logical_name": "product.zip",
        "object_key": "tenant/atomic/output/abc",
        "media_type": "application/zip",
        "format": "zip",
        "checksum_sha256": "a" * 64,
        "size_bytes": 10,
        "metadata": {"request_id": "atomic"},
    }
    with pytest.raises(LeaseLost):
        repo.complete_with_artifact(
            tenant_id="tenant-atomic", job_id=job["job_id"],
            lease_token=uuid.uuid4(), result_manifest={"request_id": "atomic"},
            artifact=artifact,
        )
    import psycopg
    with psycopg.connect(repo._dsn) as conn:
        orphan_metadata_count = conn.execute(
            "select count(*) from foundry.artifacts where tenant_id = %s and object_key = %s",
            ("tenant-atomic", artifact["object_key"]),
        ).fetchone()[0]
    assert orphan_metadata_count == 0
    completed, registered = repo.complete_with_artifact(
        tenant_id="tenant-atomic", job_id=job["job_id"],
        lease_token=claimed["lease_token"], result_manifest={"request_id": "atomic"},
        artifact=artifact,
    )
    assert completed["status"] == "succeeded"
    assert completed["result_manifest"]["artifact_id"] == str(registered["artifact_id"])
    assert repo.get(tenant_id="tenant-atomic", job_id=job["job_id"])["status"] == "succeeded"
