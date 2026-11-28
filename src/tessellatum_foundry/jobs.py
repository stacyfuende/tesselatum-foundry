"""Durable, tenant-scoped Postgres job repository for Foundry.

This module manages control-plane metadata only. Spatial execution and artifact
bytes remain outside the database. Install the optional postgis extra to use it.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

_SECRET_KEY = re.compile(
    r"(?:^|_)(?:authorization|access_token|refresh_token|password|passwd|secret|"
    r"api_key|private_key|source_bytes|file_bytes|raw_data|data_url)(?:$|_)",
    re.IGNORECASE,
)


class JobRepositoryError(RuntimeError):
    """Base class for durable job repository errors."""


class IdempotencyConflict(JobRepositoryError):
    """An idempotency key was reused for a different semantic request."""


class JobNotFound(JobRepositoryError):
    """The tenant-scoped job does not exist."""


class LeaseLost(JobRepositoryError):
    """The worker no longer owns the job lease."""


def _identifier(value: str, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be a non-empty string of at most {maximum} characters.")
    return value.strip()


def _validate_metadata(value: Any, path: str = "request_payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings.")
            if _SECRET_KEY.search(key):
                raise ValueError(f"Sensitive field {path}.{key} must not be persisted.")
            _validate_metadata(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_metadata(child, f"{path}[{index}]")
    elif isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ValueError(f"{path} must not contain non-finite numbers.")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{path} contains unsupported value type {type(value).__name__}.")


def canonical_request_sha256(request_version: str, request_payload: dict[str, Any]) -> str:
    """Hash the semantic request envelope using stable JSON encoding."""
    _identifier(request_version, "request_version", 32)
    if not isinstance(request_payload, dict):
        raise ValueError("request_payload must be an object.")
    _validate_metadata(request_payload)
    canonical = json.dumps(
        {"request_version": request_version, "request_payload": request_payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class PostgresJobRepository:
    """Tenant-scoped job lifecycle repository backed by psycopg 3.

    Tenant and actor identifiers must come from trusted authentication, never
    request JSON. Every operation scopes queries by the authenticated tenant.
    A custom connection factory may be supplied for controlled environments.
    """

    def __init__(self, dsn: str | None = None, connect: Callable[..., Any] | None = None):
        if connect is None and not dsn:
            raise ValueError("Provide a Postgres DSN or connection factory.")
        self._dsn = dsn
        self._connect_factory = connect

    def _connection(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install tessellatum-foundry[postgis] to use Postgres jobs.") from exc
        return psycopg.connect(self._dsn, row_factory=dict_row)

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        if not isinstance(value, dict):
            raise ValueError("Metadata must be a JSON object.")
        _validate_metadata(value)
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    def submit(
        self, *, tenant_id: str, actor_id: str, idempotency_key: str,
        request_version: str, request_payload: dict[str, Any], max_attempts: int = 3,
    ) -> dict[str, Any]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        actor_id = _identifier(actor_id, "actor_id")
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        request_version = _identifier(request_version, "request_version", 32)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be an integer between 1 and 20.")
        digest = canonical_request_sha256(request_version, request_payload)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into foundry.jobs
                        (tenant_id, actor_id, idempotency_key, request_version,
                         request_sha256, request_payload, max_attempts)
                    values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                    on conflict (tenant_id, idempotency_key) do nothing
                    returning *
                    """,
                    (tenant_id, actor_id, idempotency_key, request_version,
                     digest, self._json(request_payload), max_attempts),
                )
                job = cur.fetchone()
                if job is None:
                    cur.execute(
                        """select * from foundry.jobs
                           where tenant_id = %s and idempotency_key = %s for update""",
                        (tenant_id, idempotency_key),
                    )
                    job = cur.fetchone()
                    if job is None:
                        raise JobRepositoryError("Idempotent submission conflicted but no job was found.")
                    if job["request_sha256"] != digest:
                        raise IdempotencyConflict(
                            "This tenant has already used the idempotency key for a different request."
                        )
                    return job
                cur.execute(
                    """insert into foundry.job_events
                       (tenant_id, job_id, event_type, from_status, to_status, detail)
                       values (%s, %s, 'submitted', null, 'queued', '{}'::jsonb)""",
                    (tenant_id, job["job_id"]),
                )
                return job

    def get(self, *, tenant_id: str, job_id: uuid.UUID | str) -> dict[str, Any]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select * from foundry.jobs where tenant_id = %s and job_id = %s",
                    (tenant_id, job_id),
                )
                row = cur.fetchone()
        if row is None:
            raise JobNotFound("Job not found for this tenant.")
        return row

    def list_events(self, *, tenant_id: str, job_id: uuid.UUID | str) -> list[dict[str, Any]]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """select event_id, tenant_id, job_id, event_type, from_status,
                              to_status, detail, occurred_at
                       from foundry.job_events
                       where tenant_id = %s and job_id = %s
                       order by occurred_at, event_id""",
                    (tenant_id, job_id),
                )
                return list(cur.fetchall())

    def claim_next(self, *, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        worker_id = _identifier(worker_id, "worker_id")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be an integer between 5 and 3600.")
        token = uuid.uuid4()
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    with candidate as (
                        select job_id, tenant_id from foundry.jobs
                        where status = 'queued' and available_at <= now()
                          and attempt_count < max_attempts
                        order by available_at, created_at
                        for update skip locked limit 1
                    )
                    update foundry.jobs j
                    set status = 'running', attempt_count = j.attempt_count + 1,
                        lease_token = %s,
                        lease_expires_at = now() + make_interval(secs => %s),
                        started_at = coalesce(j.started_at, now()), updated_at = now()
                    from candidate c
                    where j.job_id = c.job_id and j.tenant_id = c.tenant_id
                    returning j.*
                    """,
                    (token, lease_seconds),
                )
                job = cur.fetchone()
                if job is None:
                    return None
                cur.execute(
                    """insert into foundry.job_events
                       (tenant_id, job_id, event_type, from_status, to_status, detail)
                       values (%s, %s, 'claimed', 'queued', 'running', %s::jsonb)""",
                    (job["tenant_id"], job["job_id"],
                     self._json({"worker_id": worker_id, "attempt": job["attempt_count"]})),
                )
                return job

    def heartbeat(
        self, *, tenant_id: str, job_id: uuid.UUID | str,
        lease_token: uuid.UUID | str, lease_seconds: int = 120,
    ) -> datetime:
        tenant_id = _identifier(tenant_id, "tenant_id")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be an integer between 5 and 3600.")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update foundry.jobs
                       set lease_expires_at = now() + make_interval(secs => %s), updated_at = now()
                       where tenant_id = %s and job_id = %s and status = 'running'
                         and lease_token = %s and lease_expires_at > now()
                       returning lease_expires_at""",
                    (lease_seconds, tenant_id, job_id, lease_token),
                )
                row = cur.fetchone()
        if row is None:
            raise LeaseLost("Worker lease is missing, expired, or no longer owned by this worker.")
        return row["lease_expires_at"]

    def complete(
        self, *, tenant_id: str, job_id: uuid.UUID | str,
        lease_token: uuid.UUID | str, result_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        manifest = self._json(result_manifest)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update foundry.jobs
                       set status = 'succeeded', result_manifest = %s::jsonb,
                           lease_token = null, lease_expires_at = null,
                           finished_at = now(), updated_at = now()
                       where tenant_id = %s and job_id = %s and status = 'running'
                         and lease_token = %s and lease_expires_at > now()
                       returning *""",
                    (manifest, tenant_id, job_id, lease_token),
                )
                job = cur.fetchone()
                if job is None:
                    raise LeaseLost("Cannot complete a job without its active lease.")
                cur.execute(
                    """insert into foundry.job_events
                       (tenant_id, job_id, event_type, from_status, to_status, detail)
                       values (%s, %s, 'completed', 'running', 'succeeded', '{}'::jsonb)""",
                    (tenant_id, job_id),
                )
                return job

    def fail(
        self, *, tenant_id: str, job_id: uuid.UUID | str,
        lease_token: uuid.UUID | str, error: dict[str, Any],
        retryable: bool = True, retry_delay_seconds: int = 30,
    ) -> dict[str, Any]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        error_json = self._json(error)
        if not isinstance(retry_delay_seconds, int) or isinstance(retry_delay_seconds, bool) or not 0 <= retry_delay_seconds <= 86400:
            raise ValueError("retry_delay_seconds must be an integer between 0 and 86400.")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update foundry.jobs
                       set status = case when %s and attempt_count < max_attempts
                                         then 'queued' else 'failed' end,
                           available_at = case when %s and attempt_count < max_attempts
                                               then now() + make_interval(secs => %s)
                                               else available_at end,
                           last_error = %s::jsonb,
                           finished_at = case when %s and attempt_count < max_attempts
                                              then null else now() end,
                           lease_token = null, lease_expires_at = null, updated_at = now()
                       where tenant_id = %s and job_id = %s and status = 'running'
                         and lease_token = %s and lease_expires_at > now()
                       returning *""",
                    (retryable, retryable, retry_delay_seconds, error_json, retryable,
                     tenant_id, job_id, lease_token),
                )
                job = cur.fetchone()
                if job is None:
                    raise LeaseLost("Cannot fail a job without its active lease.")
                event = "retry_scheduled" if job["status"] == "queued" else "failed"
                cur.execute(
                    """insert into foundry.job_events
                       (tenant_id, job_id, event_type, from_status, to_status, detail)
                       values (%s, %s, %s, 'running', %s, %s::jsonb)""",
                    (tenant_id, job_id, event, job["status"], error_json),
                )
                return job

    def reap_expired_leases(self) -> list[dict[str, Any]]:
        """Fence expired workers and requeue or time out their jobs atomically."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    with expired as (
                        update foundry.jobs
                        set status = case when attempt_count < max_attempts
                                          then 'queued' else 'timed_out' end,
                            available_at = now(), lease_token = null, lease_expires_at = null,
                            finished_at = case when attempt_count < max_attempts
                                               then null else now() end,
                            updated_at = now()
                        where status = 'running' and lease_expires_at <= now()
                        returning *
                    ), logged as (
                        insert into foundry.job_events
                            (tenant_id, job_id, event_type, from_status, to_status, detail)
                        select tenant_id, job_id,
                               case when status = 'queued' then 'lease_expired_requeued'
                                    else 'lease_expired_timed_out' end,
                               'running', status, '{}'::jsonb
                        from expired returning job_id
                    )
                    select expired.* from expired join logged using (job_id)
                    """,
                )
                return list(cur.fetchall())

    def record_artifact(
        self, *, tenant_id: str, job_id: uuid.UUID | str, artifact_kind: str,
        logical_name: str, object_key: str, media_type: str, checksum_sha256: str,
        size_bytes: int, format: str | None = None, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum_sha256):
            raise ValueError("checksum_sha256 must be a lowercase SHA-256 hex digest.")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer.")
        metadata_json = self._json(metadata or {})
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into foundry.artifacts
                       (tenant_id, job_id, artifact_kind, logical_name, object_key,
                        media_type, format, checksum_sha256, size_bytes, metadata)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                       returning *""",
                    (tenant_id, job_id, artifact_kind, logical_name, object_key,
                     media_type, format, checksum_sha256, size_bytes, metadata_json),
                )
                row = cur.fetchone()
                if row is None:  # pragma: no cover
                    raise JobRepositoryError("Artifact insert returned no row.")
                return row
