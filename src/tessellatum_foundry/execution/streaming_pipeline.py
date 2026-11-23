"""End-to-end bounded batch execution for an already-queued streaming Run."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from tessellatum_foundry.execution.batches import VectorBufferBatchExecutor
from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.execution.streaming import (
    StreamingFinalizationResult,
    StreamingRunFinalizer,
)
from tessellatum_foundry.sources.batches import FeatureBatch
from tessellatum_foundry.storage.artifacts import utc_timestamp
from tessellatum_foundry.storage.streaming import (
    StreamingFeatureCollectionTransaction,
    StreamingTransactionError,
)
from tessellatum_foundry.validation.streaming import VectorBufferStreamingValidator


@dataclass(frozen=True)
class StreamingExecutionResult:
    """Run, Artifact, validation report and bounded stream measurements."""

    finalized: StreamingFinalizationResult
    validation_report: dict[str, Any]
    batch_count: int
    feature_count: int
    duration_ms: int


class StreamingVectorBufferPipeline:
    """Connect external batches, worker execution, criticism and publication.

    The caller creates and starts the Run, resolves the source adapter and
    constructs a private transaction. This pipeline owns the critical ordering:
    exhaust the source (including its EOF integrity check), validate all batch
    pairs, seal the input, persist the aggregate critic report, then publish.
    It never stages source bytes or holds more than one input/output batch pair.
    """

    def __init__(
        self,
        *,
        executor: VectorBufferBatchExecutor,
        validator: VectorBufferStreamingValidator,
        finalizer: StreamingRunFinalizer,
        run_repository: RunRepository,
    ) -> None:
        self.executor = executor
        self.validator = validator
        self.finalizer = finalizer
        self.run_repository = run_repository

    def execute(
        self,
        batches: Iterable[FeatureBatch],
        *,
        transaction: StreamingFeatureCollectionTransaction,
        capability_version: str,
        input_crs: dict[str, Any],
        measurement_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str,
        source_completion: dict[str, Any],
        artifact_id: str,
        artifact_version: str,
        output_port: str,
        created_by: str,
        output_crs: dict[str, Any],
        media_type: str = "application/geo+json",
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StreamingExecutionResult:
        run = self.run_repository.get_run(transaction.run_id)
        if run.get("status") != "running" or run.get("attempt") != transaction.attempt:
            raise RunStateError("Streaming transaction must belong to the active Run attempt.")
        if run.get("capability") != {
            "capability_id": "vector.buffer",
            "version": capability_version,
        }:
            raise RunStateError("Run Capability does not match the streaming worker contract.")
        safe_completion_fields = {
            "provider",
            "dataset_id",
            "resource_id",
            "version",
            "etag",
            "checksum_sha256",
            "media_type",
            "byte_count",
            "source_modified_at",
        }
        if (
            not isinstance(source_completion, dict)
            or set(source_completion) - safe_completion_fields
        ):
            raise StreamingTransactionError(
                "Source completion evidence contains unsupported or potentially sensitive fields."
            )

        batch_count = 0
        feature_count = 0
        duration_ms = 0
        try:
            # Iterating to exhaustion is significant: source adapters verify
            # end-of-stream checksums only after their final yielded chunk.
            for batch in batches:
                processed = self.executor.execute(
                    batch,
                    capability_version=capability_version,
                    input_crs=input_crs,
                    measurement_crs=measurement_crs,
                    parameters=parameters,
                    runtime_image_digest=runtime_image_digest,
                )
                self.validator.add(batch, processed)
                transaction.append(processed)
                batch_count += 1
                feature_count += batch.feature_count
                duration_ms += processed.duration_ms

            # Reaching this point means the iterator terminated normally; source
            # adapters perform checksum/ETag checks as part of that termination.
            completion = dict(source_completion)
            completion.update({
                "eof_verified": True,
                "batch_count": batch_count,
                "feature_count": feature_count,
            })
            transaction.seal_input(completion)
            aggregate = self.validator.finish()
            report = aggregate.as_validation_report(transaction.run_id)
            self.run_repository.save_validation_report(report)

            if not aggregate.passed:
                transaction.abort("validation.output_failed")
                self.run_repository.transition(
                    transaction.run_id,
                    expected_status="running",
                    new_status="failed",
                    fields={
                        "finished_at": utc_timestamp(),
                        "error": {
                            "code": "streaming.output_validation_failed",
                            "message": (
                                "The streamed output did not satisfy the execution-output contract."
                            ),
                            "retryable": False,
                        },
                        "validation_report_ids": [report["report_id"]],
                    },
                    event_type="streaming_output_rejected",
                )
                raise StreamingTransactionError(
                    "Streamed output failed independent validation; no Artifact was published."
                )

            transaction.seal_output()
            transaction.mark_validated({
                "passed": True,
                "report_id": report["report_id"],
                "batch_count": batch_count,
                "feature_count": feature_count,
            })
            finalized = self.finalizer.finalize(
                transaction,
                artifact_id=artifact_id,
                artifact_version=artifact_version,
                output_port=output_port,
                validation_report_id=report["report_id"],
                created_by=created_by,
                media_type=media_type,
                format_name="geojson",
                spatial={
                    "kind": "vector",
                    "crs": output_crs,
                    "geometry_types": list(aggregate.geometry_types),
                },
                rights=rights,
                metadata={
                    **(metadata or {}),
                    "streaming": {
                        "batch_count": batch_count,
                        "feature_count": feature_count,
                        "runtime_image_digest": aggregate.runtime_image_digest,
                    },
                },
                resource_usage={"duration_ms": duration_ms},
            )
            return StreamingExecutionResult(
                finalized=finalized,
                validation_report=report,
                batch_count=batch_count,
                feature_count=feature_count,
                duration_ms=duration_ms,
            )
        except Exception as error:
            # A validated transaction is deliberately left intact: publication
            # may have committed before a process interruption, and the recovery
            # finalizer must reconcile it rather than discard evidence.
            if transaction.state in {"open", "input_sealed", "output_sealed"}:
                try:
                    transaction.abort("streaming.execution_interrupted")
                except StreamingTransactionError:
                    pass
            current = self.run_repository.get_run(transaction.run_id)
            if current.get("status") == "running" and transaction.state != "validated":
                self.run_repository.transition(
                    transaction.run_id,
                    expected_status="running",
                    new_status="failed",
                    fields={
                        "finished_at": utc_timestamp(),
                        "error": {
                            "code": "streaming.execution_failed",
                            "message": f"Streaming execution stopped ({type(error).__name__}).",
                            "retryable": True,
                        },
                    },
                    event_type="streaming_execution_failed",
                )
            raise
