"""Bounded, cross-batch validation for streamed vector.buffer output."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from tessellatum_foundry.execution.batches import ProcessedFeatureBatch
from tessellatum_foundry.sources.batches import FeatureBatch
from tessellatum_foundry.validation.output import (
    OutputFinding,
    inspect_vector_buffer_output,
)


class StreamingValidationError(ValueError):
    """Raised when streamed validation receives inconsistent batch evidence."""


@dataclass(frozen=True)
class StreamingVectorValidationReport:
    """Compact aggregate evidence; no complete input or output is retained."""

    geometry_types: tuple[str, ...]
    findings: tuple[OutputFinding, ...]
    batch_count: int
    feature_count: int
    duration_ms: int
    runtime_image_digest: str

    @property
    def passed(self) -> bool:
        return self.batch_count > 0 and all(
            finding.status == "passed" for finding in self.findings
        )

    def as_validation_report(self, run_id: str) -> dict[str, Any]:
        """Serialize aggregate findings in Foundry's execution-output report shape."""
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string.")
        passed = self.passed
        return {
            "report_id": f"report:{run_id}:output",
            "subject": {"kind": "run", "id": run_id},
            "stage": "execution_output",
            "overall_status": "passed" if passed else "failed",
            "validator": {
                "name": "foundry-spatial-output-critic",
                "version": "0.3.0",
            },
            "findings": [
                {
                    "code": finding.code,
                    "severity": finding.severity,
                    "status": finding.status,
                    "message": finding.message,
                    "json_pointer": finding.json_pointer,
                }
                for finding in self.findings
            ],
            "summary": (
                f"Validated {self.feature_count} features across "
                f"{self.batch_count} bounded batches."
                if passed
                else "One or more streamed output contract checks failed."
            ),
            "assessed_dimensions": [
                "feature_count",
                "feature_metadata",
                "crs",
                "geometry_type",
                "geometry_validity",
                "coordinate_finiteness",
                "dimensionality",
                "batch_continuity",
                "worker_identity",
            ],
            "unassessed_dimensions": [
                "methodological_suitability",
                "rights_security_policy",
            ],
            "stream_evidence": {
                "batch_count": self.batch_count,
                "feature_count": self.feature_count,
                "duration_ms": self.duration_ms,
                "runtime_image_digest": self.runtime_image_digest,
                "geometry_types": list(self.geometry_types),
            },
        }


class VectorBufferStreamingValidator:
    """Validate paired input/output batches and aggregate bounded evidence.

    This validates each batch independently with the existing spatial critic,
    then aggregates findings and enforces stream-wide sequence, offset, count,
    and worker-image invariants. Memory use is proportional to one batch plus
    the small set of finding codes and geometry types.
    """

    def __init__(
        self,
        *,
        input_crs: dict[str, Any],
        expected_output_crs: dict[str, Any],
        permitted_geometry_types: set[str],
    ) -> None:
        if not permitted_geometry_types:
            raise ValueError("permitted_geometry_types must not be empty.")
        self.input_crs = input_crs
        self.expected_output_crs = expected_output_crs
        self.permitted_geometry_types = set(permitted_geometry_types)
        self._next_sequence = 0
        self._next_offset = 0
        self._batch_count = 0
        self._feature_count = 0
        self._duration_ms = 0
        self._runtime_image_digest: str | None = None
        self._geometry_types: set[str] = set()
        self._findings: dict[str, tuple[bool, str, str]] = {}

    def add(
        self,
        input_batch: FeatureBatch,
        output_batch: ProcessedFeatureBatch,
    ) -> None:
        """Validate one matching pair without retaining either batch."""
        if not isinstance(input_batch, FeatureBatch) or not isinstance(
            output_batch, ProcessedFeatureBatch
        ):
            raise StreamingValidationError("Input and output batch types are invalid.")
        if (
            input_batch.sequence != self._next_sequence
            or output_batch.sequence != self._next_sequence
            or input_batch.first_feature_offset != self._next_offset
            or output_batch.first_feature_offset != self._next_offset
            or input_batch.feature_count != output_batch.feature_count
        ):
            raise StreamingValidationError(
                "Streamed input/output batch sequence, offset, or count is not contiguous."
            )
        if hashlib.sha256(input_batch.payload).hexdigest() != input_batch.checksum_sha256:
            raise StreamingValidationError("Input batch checksum verification failed.")
        if output_batch.input_checksum_sha256 != input_batch.checksum_sha256:
            raise StreamingValidationError(
                "Processed batch does not identify the exact input batch checksum."
            )
        if hashlib.sha256(output_batch.payload).hexdigest() != output_batch.output_checksum_sha256:
            raise StreamingValidationError("Output batch checksum verification failed.")
        if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", output_batch.runtime_image_digest):
            raise StreamingValidationError("Worker image digest is not immutable SHA-256 identity.")
        if self._runtime_image_digest is None:
            self._runtime_image_digest = output_batch.runtime_image_digest
        elif self._runtime_image_digest != output_batch.runtime_image_digest:
            raise StreamingValidationError("Worker image identity changed between batches.")
        if (
            isinstance(output_batch.duration_ms, bool)
            or not isinstance(output_batch.duration_ms, int)
            or output_batch.duration_ms < 0
        ):
            raise StreamingValidationError("Batch duration must be a non-negative integer.")

        try:
            source_collection = json.loads(input_batch.payload)
            result_collection = json.loads(output_batch.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StreamingValidationError("A batch payload is not valid UTF-8 JSON.") from error
        if (
            not isinstance(source_collection, dict)
            or source_collection.get("type") != "FeatureCollection"
            or not isinstance(source_collection.get("features"), list)
            or len(source_collection["features"]) != input_batch.feature_count
        ):
            raise StreamingValidationError("Input FeatureCollection does not match batch metadata.")

        inspection = inspect_vector_buffer_output(
            input_feature_collection=source_collection,
            output_feature_collection=result_collection,
            input_crs=self.input_crs,
            expected_output_crs=self.expected_output_crs,
            actual_output_crs=self.expected_output_crs,
            permitted_geometry_types=self.permitted_geometry_types,
        )
        for finding in inspection.findings:
            previous = self._findings.get(finding.code)
            passed = finding.status == "passed"
            if previous is None:
                self._findings[finding.code] = (
                    passed,
                    finding.message,
                    finding.json_pointer,
                )
            else:
                self._findings[finding.code] = (
                    previous[0] and passed,
                    previous[1] if previous[0] and passed else finding.message,
                    previous[2],
                )
        self._geometry_types.update(inspection.geometry_types)
        self._batch_count += 1
        self._feature_count += input_batch.feature_count
        self._duration_ms += output_batch.duration_ms
        self._next_sequence += 1
        self._next_offset += input_batch.feature_count

    def finish(self) -> StreamingVectorValidationReport:
        """Freeze aggregate evidence; an empty stream is never considered valid."""
        findings = [
            OutputFinding(
                code=code,
                status="passed" if passed else "failed",
                severity="info" if passed else "error",
                message=message,
                json_pointer=pointer,
            )
            for code, (passed, message, pointer) in sorted(self._findings.items())
        ]
        if self._batch_count == 0:
            findings.append(
                OutputFinding(
                    code="output.feature_collection",
                    status="failed",
                    severity="error",
                    message="Stream contained no feature batches.",
                    json_pointer="/features",
                )
            )
        if self._runtime_image_digest is None:
            findings.append(
                OutputFinding(
                    code="output.worker_identity",
                    status="failed",
                    severity="error",
                    message="No pinned worker image identity was recorded.",
                    json_pointer="/worker/runtime_image_digest",
                )
            )
        return StreamingVectorValidationReport(
            geometry_types=tuple(sorted(self._geometry_types)),
            findings=tuple(findings),
            batch_count=self._batch_count,
            feature_count=self._feature_count,
            duration_ms=self._duration_ms,
            runtime_image_digest=self._runtime_image_digest or "",
        )
