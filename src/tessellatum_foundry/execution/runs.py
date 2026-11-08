"""Durable local Run and Validation Report records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.storage.artifacts import utc_timestamp


_TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
_ALLOWED_TRANSITIONS = {
    "queued": {"running", "failed", "cancelled"},
    "waiting_for_resources": {"running", "failed", "cancelled", "timed_out"},
    "running": {"succeeded", "failed", "cancelled", "timed_out"},
}


class RunStateError(RuntimeError):
    """Raised for invalid or post-terminal Run state changes."""


class RunRepository:
    """JSON-backed local control-plane repository for Run lifecycle records.

    Updates are serialized within one process. A database-backed repository will
    provide distributed concurrency control when the control plane is deployed.
    """

    def __init__(self, root: Path, contracts: ContractRegistry | None = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.contracts = contracts or ContractRegistry()
        self._lock = threading.RLock()

    def create_queued_run(
        self,
        *,
        run_id: str,
        cell: dict[str, str],
        capability: dict[str, str],
        input_snapshots: list[dict[str, Any]],
        normalized_parameters: dict[str, Any],
        attempt: int = 1,
        retry_of_run_id: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "run_id": run_id,
            "attempt": attempt,
            "cell": cell,
            "capability": capability,
            "status": "queued",
            "created_at": utc_timestamp(),
            "input_snapshots": input_snapshots,
            "normalized_parameters": normalized_parameters,
            "events": [{"timestamp": utc_timestamp(), "event_type": "run_queued"}],
        }
        if retry_of_run_id is not None:
            record["retry_of_run_id"] = retry_of_run_id
        self.contracts.validate("run.schema.json", record)
        path = self._run_path(run_id)
        with self._lock:
            if path.exists():
                raise RunStateError(f"Run {run_id} already exists.")
            self._write_atomic(path, record, replace=False)
        return record

    def get_run(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"Run {run_id} was not found.")
        record = json.loads(path.read_text(encoding="utf-8"))
        self.contracts.validate("run.schema.json", record)
        return record

    def transition(
        self,
        run_id: str,
        *,
        expected_status: str,
        new_status: str,
        fields: dict[str, Any] | None = None,
        event_type: str,
        event_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            current = self.get_run(run_id)
            status = current["status"]
            if status in _TERMINAL_STATES:
                raise RunStateError(f"Terminal Run {run_id} is immutable.")
            if status != expected_status:
                raise RunStateError(
                    f"Run {run_id} is {status!r}, not expected {expected_status!r}."
                )
            if new_status not in _ALLOWED_TRANSITIONS.get(status, set()):
                raise RunStateError(f"Invalid Run transition: {status} -> {new_status}.")
            updated = dict(current)
            updated.update(fields or {})
            updated["status"] = new_status
            event: dict[str, Any] = {
                "timestamp": utc_timestamp(),
                "event_type": event_type,
            }
            if event_detail:
                event["detail"] = event_detail
            updated["events"] = [*current.get("events", []), event]
            self.contracts.validate("run.schema.json", updated)
            self._write_atomic(self._run_path(run_id), updated, replace=True)
            return updated

    def save_validation_report(self, report: dict[str, Any]) -> dict[str, Any]:
        self.contracts.validate("validation-report.schema.json", report)
        path = self._report_path(report["report_id"])
        with self._lock:
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != report:
                    raise RunStateError(
                        f"Validation Report {report['report_id']} already exists."
                    )
                return existing
            self._write_atomic(path, report, replace=False)
        return report

    def get_validation_report(self, report_id: str) -> dict[str, Any]:
        path = self._report_path(report_id)
        if not path.is_file():
            raise FileNotFoundError(f"Validation Report {report_id} was not found.")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.contracts.validate("validation-report.schema.json", report)
        return report

    def _run_path(self, run_id: str) -> Path:
        key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self.root / "runs" / f"{key}.json"

    def _report_path(self, report_id: str) -> Path:
        key = hashlib.sha256(report_id.encode("utf-8")).hexdigest()
        return self.root / "reports" / f"{key}.json"

    @staticmethod
    def _write_atomic(path: Path, record: dict[str, Any], *, replace: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".foundry-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                try:
                    os.link(temporary, path)
                except FileExistsError as error:
                    raise RunStateError(f"Record already exists: {path.name}") from error
        finally:
            temporary.unlink(missing_ok=True)
