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
_IMMUTABLE_FIELDS = {
    "run_id",
    "attempt",
    "cell",
    "capability",
    "created_at",
    "creation_sequence",
    "input_snapshots",
    "source_references",
    "normalized_parameters",
    "retry_of_run_id",
    "recipe",
    "recipe_execution_id",
    "recipe_node_id",
    "recipe_node_order",
}
_SET_ONCE_FIELDS = {
    "started_at",
    "worker",
    "implementation",
    "runtime_image_digest",
    "cache",
}
_ALLOWED_TRANSITION_FIELDS = {
    ("queued", "running"): {
        "started_at",
        "worker",
        "implementation",
        "runtime_image_digest",
        "cache",
    },
    ("queued", "failed"): {"finished_at", "error"},
    ("queued", "cancelled"): {"finished_at", "error"},
    ("waiting_for_resources", "running"): {
        "started_at",
        "worker",
        "implementation",
        "runtime_image_digest",
    },
    ("waiting_for_resources", "failed"): {"finished_at", "error"},
    ("waiting_for_resources", "cancelled"): {"finished_at", "error"},
    ("waiting_for_resources", "timed_out"): {"finished_at", "error"},
    ("running", "succeeded"): {
        "finished_at",
        "outputs",
        "validation_report_ids",
        "resource_usage",
    },
    ("running", "failed"): {
        "finished_at",
        "error",
        "validation_report_ids",
    },
    ("running", "cancelled"): {"finished_at", "error"},
    ("running", "timed_out"): {"finished_at", "error"},
}
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
        self._creation_sequence = self._load_creation_sequence()

    def create_queued_run(
        self,
        *,
        run_id: str,
        cell: dict[str, str],
        capability: dict[str, str],
        input_snapshots: list[dict[str, Any]],
        normalized_parameters: dict[str, Any],
        source_references: list[dict[str, Any]] | None = None,
        attempt: int = 1,
        retry_of_run_id: str | None = None,
        recipe: dict[str, str] | None = None,
        recipe_execution_id: str | None = None,
        recipe_node_id: str | None = None,
        recipe_node_order: int | None = None,
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
            **({"source_references": source_references} if source_references else {}),
            "events": [{"timestamp": utc_timestamp(), "event_type": "run_queued"}],
        }
        if retry_of_run_id is not None:
            record["retry_of_run_id"] = retry_of_run_id
        if recipe is not None:
            record["recipe"] = recipe
        if recipe_execution_id is not None:
            record["recipe_execution_id"] = recipe_execution_id
        if recipe_node_id is not None:
            record["recipe_node_id"] = recipe_node_id
        if recipe_node_order is not None:
            record["recipe_node_order"] = recipe_node_order
        self.contracts.validate("run.schema.json", record)
        path = self._run_path(run_id)
        with self._lock:
            if path.exists():
                raise RunStateError(f"Run {run_id} already exists.")
            self._creation_sequence += 1
            record["creation_sequence"] = self._creation_sequence
            self.contracts.validate("run.schema.json", record)
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
            changes = fields or {}
            for name in _IMMUTABLE_FIELDS:
                if name in changes and changes[name] != current.get(name):
                    raise RunStateError(
                        f"Run provenance field {name!r} is immutable."
                    )
            for name in _SET_ONCE_FIELDS:
                if (
                    name in changes
                    and name in current
                    and changes[name] != current[name]
                ):
                    raise RunStateError(
                        f"Run execution identity field {name!r} cannot be changed."
                    )
            permitted_fields = _ALLOWED_TRANSITION_FIELDS[(status, new_status)]
            unexpected_fields = set(changes) - permitted_fields
            if unexpected_fields:
                names = ", ".join(sorted(unexpected_fields))
                raise RunStateError(
                    f"Fields {names} are not permitted for transition "
                    f"{status} -> {new_status}."
                )
            updated = dict(current)
            updated.update(changes)
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

    def reconcile_committed_output(
        self,
        run_id: str,
        *,
        artifact_store: Any,
        artifact_id: str,
        artifact_version: str,
        output_port: str,
        validation_report_id: str,
        resource_usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete a running Run after independently verifying committed output.

        Safe to call after restart: an already-succeeded Run is returned only
        when its output and validation references exactly match this request.
        """
        artifact = artifact_store.get_artifact(artifact_id, artifact_version)
        artifact_store.verify_artifact(artifact)
        current = self.get_run(run_id)
        if (
            artifact.get("metadata", {}).get("producer_run_id") != run_id
            or artifact.get("metadata", {}).get("producer_run_attempt") != current["attempt"]
        ):
            raise RunStateError("Artifact producer identity does not match this Run attempt.")
        report = self.get_validation_report(validation_report_id)
        if (
            report.get("subject") != {"kind": "run", "id": run_id}
            or report.get("stage") != "execution_output"
            or report.get("overall_status") != "passed"
        ):
            raise RunStateError("A passing execution-output report for this Run is required.")

        output = {
            "output_port": output_port,
            "artifact": {"artifact_id": artifact_id, "version": artifact_version},
        }
        if current["status"] == "succeeded":
            if (
                current.get("outputs") == [output]
                and validation_report_id in current.get("validation_report_ids", [])
            ):
                return current
            raise RunStateError(
                "Succeeded Run does not match the committed output being reconciled."
            )
        if current["status"] != "running":
            raise RunStateError("Only a running Run can be reconciled to succeeded.")

        fields: dict[str, Any] = {
            "finished_at": utc_timestamp(),
            "outputs": [output],
            "validation_report_ids": [validation_report_id],
        }
        if resource_usage is not None:
            fields["resource_usage"] = resource_usage
        return self.transition(
            run_id,
            expected_status="running",
            new_status="succeeded",
            fields=fields,
            event_type="run_output_reconciled",
            event_detail={
                "artifact_id": artifact_id,
                "artifact_version": artifact_version,
                "artifact_checksum_sha256": artifact["checksum"]["value"],
                "validation_report_id": validation_report_id,
            },
        )

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

    def list_runs(self) -> list[dict[str, Any]]:
        """List all persisted Runs in stable creation order."""
        runs_dir = self.root / "runs"
        if not runs_dir.is_dir():
            return []
        records = []
        for path in runs_dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            self.contracts.validate("run.schema.json", record)
            if self._run_path(record["run_id"]) != path:
                raise RunStateError("Stored Run identity does not match its registry path.")
            records.append(record)
        return sorted(
            records,
            key=lambda item: (
                item["created_at"],
                item.get("creation_sequence", 0),
                item["run_id"],
            ),
        )

    def list_runs_for_recipe_execution(
        self, recipe_execution_id: str
    ) -> list[dict[str, Any]]:
        """List immutable cell Runs correlated to one Recipe execution."""
        return [
            record
            for record in self.list_runs()
            if record.get("recipe_execution_id") == recipe_execution_id
        ]

    def list_cache_candidates(self, cache_key: str) -> list[dict[str, Any]]:
        """Return successful Runs with the exact cache key, newest first."""
        candidates = [
            record
            for record in self.list_runs()
            if record["status"] == "succeeded"
            and record.get("cache", {}).get("cache_key") == cache_key
            and record.get("outputs")
            and record.get("validation_report_ids")
        ]
        return sorted(
            candidates,
            key=lambda item: (item.get("finished_at", ""), item["run_id"]),
            reverse=True,
        )

    def get_validation_report(self, report_id: str) -> dict[str, Any]:
        path = self._report_path(report_id)
        if not path.is_file():
            raise FileNotFoundError(f"Validation Report {report_id} was not found.")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.contracts.validate("validation-report.schema.json", report)
        return report

    def _load_creation_sequence(self) -> int:
        """Recover the latest local sequence once when opening the repository."""
        runs_dir = self.root / "runs"
        highest = 0
        record_count = 0
        if runs_dir.is_dir():
            for path in runs_dir.glob("*.json"):
                record_count += 1
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                sequence = record.get("creation_sequence") if isinstance(record, dict) else None
                if isinstance(sequence, int) and not isinstance(sequence, bool):
                    highest = max(highest, sequence)
        return max(highest, record_count)

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
