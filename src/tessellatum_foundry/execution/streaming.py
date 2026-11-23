"""Finalize streamed output publication and Run lifecycle as one orchestration step."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.streaming import (
    StreamingFeatureCollectionTransaction,
    StreamingTransactionError,
)


@dataclass(frozen=True)
class StreamingFinalizationResult:
    artifact: dict[str, Any]
    run: dict[str, Any]


class StreamingRunFinalizer:
    """Coordinate validated staging, Artifact publication and Run success."""

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_repository = run_repository

    def finalize(
        self,
        transaction: StreamingFeatureCollectionTransaction,
        *,
        artifact_id: str,
        artifact_version: str,
        output_port: str,
        validation_report_id: str,
        created_by: str,
        media_type: str = "application/geo+json",
        format_name: str = "geojson",
        spatial: dict[str, Any] | None = None,
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        resource_usage: dict[str, Any] | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> StreamingFinalizationResult:
        run = self.run_repository.get_run(transaction.run_id)
        if run["status"] != "running" or run["attempt"] != transaction.attempt:
            raise RunStateError("Streaming transaction does not belong to the active Run attempt.")
        self._require_passing_report(transaction.run_id, validation_report_id)

        artifact = transaction.publish_artifact(
            self.artifact_store,
            artifact_id=artifact_id,
            version=artifact_version,
            created_by=created_by,
            media_type=media_type,
            format_name=format_name,
            spatial=spatial,
            rights=rights,
            metadata=metadata,
            chunk_size=chunk_size,
        )
        succeeded = self.run_repository.reconcile_committed_output(
            transaction.run_id,
            artifact_store=self.artifact_store,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            output_port=output_port,
            validation_report_id=validation_report_id,
            resource_usage=resource_usage,
        )
        return StreamingFinalizationResult(artifact=artifact, run=succeeded)

    def recover_and_finalize(
        self,
        root: Path,
        transaction_id: str,
        *,
        output_port: str,
        validation_report_id: str,
        resource_usage: dict[str, Any] | None = None,
    ) -> StreamingFinalizationResult:
        transaction = StreamingFeatureCollectionTransaction.recover(
            root, transaction_id, self.artifact_store
        )
        if transaction.state != "committed":
            raise StreamingTransactionError(
                "Recovery did not find a verifiably committed Artifact; Run remains nonterminal."
            )
        identity = transaction.artifact_identity
        if identity is None:
            raise StreamingTransactionError("Committed transaction has no Artifact identity.")
        succeeded = self.run_repository.reconcile_committed_output(
            transaction.run_id,
            artifact_store=self.artifact_store,
            artifact_id=identity["artifact_id"],
            artifact_version=identity["version"],
            output_port=output_port,
            validation_report_id=validation_report_id,
            resource_usage=resource_usage,
        )
        artifact = self.artifact_store.get_artifact(
            identity["artifact_id"], identity["version"]
        )
        self.artifact_store.verify_artifact(artifact)
        return StreamingFinalizationResult(artifact=artifact, run=succeeded)

    def _require_passing_report(self, run_id: str, report_id: str) -> None:
        report = self.run_repository.get_validation_report(report_id)
        if (
            report.get("subject") != {"kind": "run", "id": run_id}
            or report.get("stage") != "execution_output"
            or report.get("overall_status") != "passed"
        ):
            raise RunStateError("A passing execution-output report for this Run is required.")
