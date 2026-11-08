"""Stable boundary between the control plane and a vector.buffer worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkerResult:
    """Untrusted result envelope returned by a worker implementation."""

    feature_collection: dict[str, Any]
    crs: dict[str, Any]
    geometry_types: tuple[str, ...]
    duration_ms: int
    runtime_image_digest: str


class VectorBufferWorker(Protocol):
    """Execution contract required by the vector.buffer Run service."""

    implementation_id: str
    implementation_version: str
    worker_id: str
    worker_type: str

    def image_digest(self) -> str:
        """Return the immutable image identity that will execute the request."""
        ...

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict[str, Any],
        measurement_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        """Execute a normalized request and return an untrusted result envelope."""
        ...
