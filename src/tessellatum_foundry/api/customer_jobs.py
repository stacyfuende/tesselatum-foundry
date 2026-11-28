"""Authenticated asynchronous customer job API with tenant-scoped reads and artifact delivery."""
from __future__ import annotations

import base64
import binascii
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from tessellatum_foundry.jobs import IdempotencyConflict, JobNotFound
from tessellatum_foundry.worker.customer_jobs import submit_customer_product_job

MAX_SOURCE = 25 * 1024 * 1024
MAX_REQUEST = 36 * 1024 * 1024


def _json_default(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": str(job["job_id"]),
        "status": job["status"],
        "request_version": job["request_version"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "attempt_count": job["attempt_count"],
        "max_attempts": job["max_attempts"],
        "result_manifest": job.get("result_manifest"),
        "last_error": (
            {"code": job["last_error"].get("code", "execution_failed")}
            if isinstance(job.get("last_error"), dict)
            else None
        ),
    }


def create_customer_jobs_server(
    address: tuple[str, int],
    *,
    authenticate: Any,
    repository: Any,
    object_store: Any,
    max_source_bytes: int = MAX_SOURCE,
    max_request_bytes: int = MAX_REQUEST,
) -> ThreadingHTTPServer:
    """Create POST /v1/jobs and tenant-scoped GET status/events/artifact routes."""
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (max_source_bytes, max_request_bytes)
    ):
        raise ValueError("Request and source limits must be positive integers.")

    class Handler(BaseHTTPRequestHandler):
        server_version = "FoundryCustomerJobs/1.0"

        def send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                default=_json_default,
                separators=(",", ":"),
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def identity(self) -> dict[str, str] | None:
            claims = authenticate(self.headers.get("Authorization", ""))
            if (
                not isinstance(claims, dict)
                or not isinstance(claims.get("tenant_id"), str)
                or not claims["tenant_id"].strip()
                or not isinstance(claims.get("actor_id"), str)
                or not claims["actor_id"].strip()
            ):
                return None
            return claims

        def do_POST(self) -> None:
            if self.path != "/v1/jobs":
                self.send_json(404, {"error": "not_found"})
                return
            claims = self.identity()
            if claims is None:
                self.send_json(401, {"error": "unauthorized"})
                return
            if (
                self.headers.get_content_type() != "application/json"
                or self.headers.get("Transfer-Encoding")
            ):
                self.send_json(415, {"error": "content_type_must_be_application_json"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.send_json(411, {"error": "content_length_required"})
                return
            if length < 1 or length > max_request_bytes:
                self.send_json(413, {"error": "request_size_limit_exceeded"})
                return
            key = self.headers.get("Idempotency-Key", "")
            if not key or len(key) > 255:
                self.send_json(400, {"error": "idempotency_key_required"})
                return
            try:
                envelope = json.loads(
                    self.rfile.read(length).decode("utf-8"),
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                )
                if (
                    not isinstance(envelope, dict)
                    or set(envelope) != {"request_version", "request", "source_file_base64"}
                    or envelope["request_version"] != "1.0.0"
                    or not isinstance(envelope["request"], dict)
                    or not isinstance(envelope["source_file_base64"], str)
                ):
                    raise ValueError("invalid envelope")
                source = base64.b64decode(envelope["source_file_base64"], validate=True)
                if not source or len(source) > max_source_bytes:
                    self.send_json(413, {"error": "source_size_limit_exceeded"})
                    return
                from tessellatum_foundry.validation.contracts import ContractRegistry

                ContractRegistry().validate(
                    "customer_product_request.schema.json", envelope["request"]
                )
                job = submit_customer_product_job(
                    repository=repository,
                    object_store=object_store,
                    tenant_id=claims["tenant_id"],
                    actor_id=claims["actor_id"],
                    idempotency_key=key,
                    request=envelope["request"],
                    source_bytes=source,
                    max_source_bytes=max_source_bytes,
                )
                self.send_json(
                    202,
                    {
                        "job": _public_job(job),
                        "status_url": f"/v1/jobs/{job['job_id']}",
                    },
                )
            except IdempotencyConflict:
                self.send_json(409, {"error": "idempotency_key_conflict"})
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                binascii.Error,
                ValueError,
                KeyError,
            ):
                self.send_json(400, {"error": "invalid_customer_submission"})
            except Exception:
                self.send_json(500, {"error": "job_submission_unavailable"})

        def do_GET(self) -> None:
            claims = self.identity()
            if claims is None:
                self.send_json(401, {"error": "unauthorized"})
                return
            parts = [part for part in urlsplit(self.path).path.split("/") if part]
            if len(parts) not in {3, 4, 5} or parts[:2] != ["v1", "jobs"]:
                self.send_json(404, {"error": "not_found"})
                return
            try:
                job_id = str(UUID(parts[2]))
                job = repository.get(tenant_id=claims["tenant_id"], job_id=job_id)
                if len(parts) == 3:
                    self.send_json(200, {"job": _public_job(job)})
                    return
                if len(parts) == 4 and parts[3] == "events":
                    events = repository.list_events(
                        tenant_id=claims["tenant_id"], job_id=job_id
                    )
                    self.send_json(
                        200,
                        {
                            "events": [
                                {
                                    "event_id": str(event["event_id"]),
                                    "event_type": event["event_type"],
                                    "from_status": event.get("from_status"),
                                    "to_status": event.get("to_status"),
                                    "occurred_at": event["occurred_at"],
                                }
                                for event in events
                            ]
                        },
                    )
                    return
                if len(parts) == 5 and parts[3] == "artifacts":
                    artifact = repository.get_artifact(
                        tenant_id=claims["tenant_id"],
                        job_id=job_id,
                        artifact_id=str(UUID(parts[4])),
                    )
                    content = object_store.get(
                        object_key=artifact["object_key"],
                        max_bytes=100 * 1024 * 1024,
                    )
                    from tessellatum_foundry.storage.object_store import verify_object

                    verify_object(
                        content,
                        expected_checksum_sha256=artifact["checksum_sha256"],
                        expected_size_bytes=artifact["size_bytes"],
                    )
                    filename = (
                        re.sub(r"[^A-Za-z0-9._-]", "_", artifact["logical_name"])[:120]
                        or "product.zip"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", artifact["media_type"])
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{filename}"',
                    )
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "private, no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                self.send_json(404, {"error": "not_found"})
            except (ValueError, JobNotFound):
                self.send_json(404, {"error": "not_found"})
            except Exception:
                self.send_json(500, {"error": "job_read_unavailable"})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer(address, Handler)
