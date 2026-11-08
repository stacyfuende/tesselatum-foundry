"""Shared worker identity and capability-specific execution protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkerResult:
    """Untrusted result envelope returned by a spatial worker implementation."""

    feature_collection: dict[str, Any]
    crs: dict[str, Any]
    duration_ms: int
    runtime_image_digest: str
    coordinate_operation: dict[str, Any] | None = None


class SpatialWorkerIdentity(Protocol):
    """Identity and immutable runtime interface common to spatial workers."""

    capability_id: str
    capability_version: str
    implementation_id: str
    implementation_version: str
    worker_id: str
    worker_type: str

    def image_digest(self) -> str:
        """Return the immutable image identity that will execute the request."""
        ...


class VectorBufferWorker(SpatialWorkerIdentity, Protocol):
    """Execution contract required by the vector.buffer Run service."""

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
        """Execute a normalized buffer request and return an untrusted result."""
        ...


class VectorReprojectWorker(SpatialWorkerIdentity, Protocol):
    """Execution contract required by the vector.reproject Run service."""

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict[str, Any],
        target_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        """Execute a normalized reprojection request and return an untrusted result."""
        ...


class CellExecutionRunner(Protocol):
    """Control-plane interface implemented by capability-specific Run services."""

    worker: SpatialWorkerIdentity
    capabilities: Any
    implementations: Any

    def validate_worker_configuration(self) -> None:
        """Verify the selected worker can execute in the current environment."""
        ...

    def execute(self, **kwargs: Any) -> Any:
        """Execute one immutable Geo-Cell and return its Run/output evidence."""
        ...
