"""Durable customer-product intake and leased execution orchestration.

This module connects the existing customer product pipeline to the job control
plane. Object bytes live behind ObjectStore; Postgres stores only bounded
metadata and opaque object keys. A real shared ObjectStore and durable tenant
runtime are deployment prerequisites, not supplied by the test adapter.
"""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import Any

from tessellatum_foundry.execution.customer_products import run_customer_spatial_product
from tessellatum_foundry.jobs import LeaseLost
from tessellatum_foundry.storage.object_store import (
    ObjectStore,
    tenant_object_key,
    verify_object,
)

REQUEST_VERSION = "1.0.0"
SOURCE_LIMIT = 25 * 1024 * 1024
OUTPUT_LIMIT = 100 * 1024 * 1024


class CustomerJobError(RuntimeError):
    """A customer job could not be safely staged or delivered."""


def submit_customer_product_job(
    *,
    repository: Any,
    object_store: ObjectStore,
    tenant_id: str,
    actor_id: str,
    idempotency_key: str,
    request: dict[str, Any],
    source_bytes: bytes,
    max_source_bytes: int = SOURCE_LIMIT,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Stage source bytes first, then submit a checksum-bound metadata job.

    Identity values must come from trusted authentication. The source object is
    immutable and tenant-namespaced; no source content is written to Postgres.
    """
    if not isinstance(request, dict):
        raise ValueError("request must be an object.")
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise ValueError("source_bytes must be non-empty bytes.")
    if len(source_bytes) > max_source_bytes:
        raise ValueError("Source file exceeds the configured intake limit.")
    source_spec = request.get("source_file")
    if not isinstance(source_spec, dict):
        raise ValueError("request must declare source_file metadata.")
    media_type = source_spec.get("media_type")
    if media_type not in {"application/geo+json", "application/json"}:
        raise ValueError("Unsupported source media type.")
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    object_identity = hashlib.sha256(
        f"{idempotency_key}:{source_digest}".encode()
    ).hexdigest()
    object_key = tenant_object_key(tenant_id, "source", object_identity)
    receipt = object_store.put(
        object_key=object_key, content=source_bytes, media_type=media_type
    )
    verify_object(
        source_bytes,
        expected_checksum_sha256=receipt.checksum_sha256,
        expected_size_bytes=receipt.size_bytes,
    )
    payload = {
        "request": request,
        "source": {
            "object_key": receipt.object_key,
            "checksum_sha256": receipt.checksum_sha256,
            "size_bytes": receipt.size_bytes,
            "media_type": receipt.media_type,
        },
    }
    return repository.submit(
        tenant_id=tenant_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_version=REQUEST_VERSION,
        request_payload=payload,
        max_attempts=max_attempts,
    )


def execute_claimed_customer_job(
    *,
    repository: Any,
    object_store: ObjectStore,
    job: dict[str, Any],
    runtime_resolver: Callable[[str], dict[str, Any]],
    product_runner: Callable[..., dict[str, Any]] = run_customer_spatial_product,
    max_source_bytes: int = SOURCE_LIMIT,
    max_output_bytes: int = OUTPUT_LIMIT,
) -> dict[str, Any]:
    """Run one already-claimed job and publish a verified ZIP artifact.

    The expensive spatial execution occurs outside database transactions.
    Lease fencing remains authoritative when the result is committed.
    """
    tenant_id = job["tenant_id"]
    job_id = job["job_id"]
    lease_token = job["lease_token"]
    payload = job["request_payload"]
    request = payload.get("request")
    source = payload.get("source")
    if not isinstance(request, dict) or not isinstance(source, dict):
        raise CustomerJobError("The queued job envelope is invalid.")
    source_bytes = object_store.get(
        object_key=source["object_key"], max_bytes=max_source_bytes
    )
    verify_object(
        source_bytes,
        expected_checksum_sha256=source["checksum_sha256"],
        expected_size_bytes=source["size_bytes"],
    )
    runtime = runtime_resolver(tenant_id)
    required = {
        "artifact_store", "capabilities", "recipe_service",
        "cell_templates", "output_bindings",
    }
    if not isinstance(runtime, dict) or not required.issubset(runtime):
        raise CustomerJobError("The tenant execution runtime is not configured.")
    result = product_runner(
        request,
        source_bytes,
        artifact_store=runtime["artifact_store"],
        capabilities=runtime["capabilities"],
        recipe_service=runtime["recipe_service"],
        cell_templates=runtime["cell_templates"],
        output_bindings=runtime["output_bindings"],
        actor_id=job["actor_id"],
        policy=runtime.get("policy"),
        max_source_bytes=max_source_bytes,
        max_export_bytes=max_output_bytes,
        contracts=runtime.get("contracts"),
    )
    if not isinstance(result, dict):
        raise CustomerJobError("The product runner returned an invalid result.")
    delivery = result.get("delivery", {})
    bundle = delivery.get("content") if isinstance(delivery, dict) else None
    if result.get("status") != "delivered" or not isinstance(bundle, bytes):
        raise CustomerJobError("The spatial product did not pass release acceptance.")
    if not bundle or len(bundle) > max_output_bytes:
        raise CustomerJobError("The generated product exceeds the delivery limit.")

    # Content-address outputs so retries with non-deterministic ZIP bytes never
    # overwrite or collide with a prior immutable publication.
    output_digest = hashlib.sha256(bundle).hexdigest()
    output_key = tenant_object_key(tenant_id, "products", output_digest)
    receipt = object_store.put(
        object_key=output_key, content=bundle, media_type="application/zip"
    )
    verify_object(
        bundle,
        expected_checksum_sha256=receipt.checksum_sha256,
        expected_size_bytes=receipt.size_bytes,
    )
    artifact = repository.record_artifact(
        tenant_id=tenant_id,
        job_id=job_id,
        artifact_kind="customer_product_bundle",
        logical_name=f"{request['request_id']}-product.zip",
        object_key=receipt.object_key,
        media_type=receipt.media_type,
        format="zip",
        checksum_sha256=receipt.checksum_sha256,
        size_bytes=receipt.size_bytes,
        metadata={
            "request_id": request["request_id"],
            "product_status": result["status"],
        },
    )
    manifest = {
        "request_id": request["request_id"],
        "artifact_id": str(artifact["artifact_id"]),
        "object_key": receipt.object_key,
        "media_type": receipt.media_type,
        "format": "zip",
        "checksum_sha256": receipt.checksum_sha256,
        "size_bytes": receipt.size_bytes,
        "acceptance_status": result.get("acceptance", {}).get("status"),
    }
    completed = repository.complete(
        tenant_id=tenant_id,
        job_id=job_id,
        lease_token=lease_token,
        result_manifest=manifest,
    )
    return {"job": completed, "artifact": artifact, "manifest": manifest}


def run_one_customer_job(
    *,
    repository: Any,
    object_store: ObjectStore,
    runtime_resolver: Callable[[str], dict[str, Any]],
    worker_id: str,
    lease_seconds: int = 120,
    heartbeat_interval_seconds: int = 30,
    product_runner: Callable[..., dict[str, Any]] = run_customer_spatial_product,
) -> dict[str, Any] | None:
    """Claim and execute at most one job, renewing its lease during processing."""
    if (
        isinstance(heartbeat_interval_seconds, bool)
        or not isinstance(heartbeat_interval_seconds, (int, float))
        or heartbeat_interval_seconds <= 0
        or heartbeat_interval_seconds >= lease_seconds
    ):
        raise ValueError("heartbeat interval must be positive and shorter than the lease.")
    job = repository.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return None
    stop = threading.Event()
    lease_errors: list[Exception] = []

    def renew() -> None:
        while not stop.wait(heartbeat_interval_seconds):
            try:
                repository.heartbeat(
                    tenant_id=job["tenant_id"],
                    job_id=job["job_id"],
                    lease_token=job["lease_token"],
                    lease_seconds=lease_seconds,
                )
            except LeaseLost:
                # Completion may win the race with the final heartbeat.
                try:
                    current = repository.get(
                        tenant_id=job["tenant_id"], job_id=job["job_id"]
                    )
                except Exception as error:
                    lease_errors.append(error)
                    stop.set()
                    return
                if current.get("status") not in {"succeeded", "failed", "cancelled", "timed_out"}:
                    lease_errors.append(LeaseLost("Worker lease was lost before completion."))
                    stop.set()
                    return
                stop.set()
            except Exception as error:
                lease_errors.append(error)
                stop.set()

    heartbeat = threading.Thread(target=renew, name="foundry-job-heartbeat", daemon=True)
    heartbeat.start()
    try:
        outcome = execute_claimed_customer_job(
            repository=repository,
            object_store=object_store,
            job=job,
            runtime_resolver=runtime_resolver,
            product_runner=product_runner,
        )
        if lease_errors:
            raise CustomerJobError("The worker lease could not be renewed.")
        return outcome
    except Exception as error:
        if lease_errors:
            raise CustomerJobError("The worker lease could not be renewed.") from error
        retryable = not isinstance(error, (ValueError, CustomerJobError))
        repository.fail(
            tenant_id=job["tenant_id"],
            job_id=job["job_id"],
            lease_token=job["lease_token"],
            error={"code": type(error).__name__},
            retryable=retryable,
        )
        return {
            "job_id": str(job["job_id"]),
            "status": "retry_scheduled" if retryable else "failed",
        }
    finally:
        stop.set()
        heartbeat.join(timeout=max(1, min(5, heartbeat_interval_seconds)))
