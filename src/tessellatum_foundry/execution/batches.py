"""Batch-aware bridge for the existing vector.buffer worker contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from tessellatum_foundry.execution.protocol import VectorBufferWorker, WorkerResult
from tessellatum_foundry.sources.batches import FeatureBatch


class BatchExecutionError(ValueError):
    """Raised when a batch or its worker result violates the batch contract."""


@dataclass(frozen=True, slots=True)
class ProcessedFeatureBatch:
    """Verified transport envelope for one independently processed input batch."""

    sequence: int
    first_feature_offset: int
    feature_count: int
    input_checksum_sha256: str
    payload: bytes
    output_checksum_sha256: str
    duration_ms: int
    runtime_image_digest: str

    @property
    def byte_size(self) -> int:
        return len(self.payload)


class VectorBufferBatchExecutor:
    """Adapt the existing whole-FeatureCollection worker to bounded batches.

    This adapter deliberately does not create or publish Artifacts and does not
    mark Runs successful. The caller must exhaust and verify the source stream,
    validate the complete output, and only then commit a durable Artifact.
    """

    def __init__(self, worker: VectorBufferWorker) -> None:
        self.worker = worker

    def execute(
        self,
        batch: FeatureBatch,
        *,
        capability_version: str,
        input_crs: dict[str, Any],
        measurement_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str,
    ) -> ProcessedFeatureBatch:
        if not isinstance(batch, FeatureBatch):
            raise BatchExecutionError("Input must be a FeatureBatch.")
        if not isinstance(batch.payload, bytes):
            raise BatchExecutionError("Input batch payload must be bytes.")
        if not isinstance(batch.checksum_sha256, str) or not re.fullmatch(
            r"[a-fA-F0-9]{64}", batch.checksum_sha256
        ):
            raise BatchExecutionError("Input batch checksum must be a SHA-256 hex digest.")
        if hashlib.sha256(batch.payload).hexdigest() != batch.checksum_sha256:
            raise BatchExecutionError("Input batch checksum verification failed.")
        for name, value, minimum in (
            ("sequence", batch.sequence, 0),
            ("first_feature_offset", batch.first_feature_offset, 0),
            ("feature_count", batch.feature_count, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise BatchExecutionError(f"Input batch {name} is invalid.")
        if not isinstance(runtime_image_digest, str) or not re.fullmatch(
            r"sha256:[a-fA-F0-9]{64}", runtime_image_digest
        ):
            raise BatchExecutionError("A pinned SHA-256 worker image digest is required.")

        try:
            collection = json.loads(batch.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BatchExecutionError("Input batch is not valid UTF-8 JSON.") from error
        if (
            not isinstance(collection, dict)
            or collection.get("type") != "FeatureCollection"
            or not isinstance(collection.get("features"), list)
            or len(collection["features"]) != batch.feature_count
        ):
            raise BatchExecutionError("Input batch payload does not match its metadata.")

        result = self.worker.execute(
            input_bytes=batch.payload,
            capability_version=capability_version,
            input_crs=input_crs,
            measurement_crs=measurement_crs,
            parameters=parameters,
            runtime_image_digest=runtime_image_digest,
        )
        if not isinstance(result, WorkerResult):
            raise BatchExecutionError("Worker returned an invalid result envelope.")
        if result.runtime_image_digest != runtime_image_digest:
            raise BatchExecutionError("Worker result image digest differs from the pinned image.")
        if (
            isinstance(result.duration_ms, bool)
            or not isinstance(result.duration_ms, int)
            or result.duration_ms < 0
        ):
            raise BatchExecutionError("Worker duration_ms must be a non-negative integer.")
        output = result.feature_collection
        if (
            not isinstance(output, dict)
            or output.get("type") != "FeatureCollection"
            or not isinstance(output.get("features"), list)
        ):
            raise BatchExecutionError("Worker output is not a GeoJSON FeatureCollection.")
        if len(output["features"]) != batch.feature_count:
            raise BatchExecutionError("Worker output feature count differs from its input batch.")
        try:
            payload = json.dumps(
                output,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise BatchExecutionError("Worker output cannot be encoded as finite JSON.") from error

        return ProcessedFeatureBatch(
            sequence=batch.sequence,
            first_feature_offset=batch.first_feature_offset,
            feature_count=batch.feature_count,
            input_checksum_sha256=batch.checksum_sha256,
            payload=payload,
            output_checksum_sha256=hashlib.sha256(payload).hexdigest(),
            duration_ms=result.duration_ms,
            runtime_image_digest=result.runtime_image_digest,
        )
