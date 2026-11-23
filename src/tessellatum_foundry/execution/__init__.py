"""Foundry execution orchestration and Run lifecycle components."""

from .capabilities import CapabilityRegistry, CapabilityRegistryError
from .implementations import ImplementationRegistry, ImplementationRegistryError
from .docker_worker import (
    DockerWorker,
    DockerVectorReprojectWorker,
    WorkerExecutionError,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from .protocol import (
    SpatialWorkerIdentity,
    VectorBufferWorker,
    VectorReprojectWorker,
    WorkerResult,
)
from .batches import BatchExecutionError, ProcessedFeatureBatch, VectorBufferBatchExecutor
from .remote_worker import RemoteVectorBufferWorker, RemoteVectorReprojectWorker
from .runs import RunRepository, RunStateError
from .streaming import StreamingFinalizationResult, StreamingRunFinalizer
from .service import (
    ExecutionPreconditionError,
    ExecutionResult,
    VectorBufferRunService,
)
from .reproject_service import VectorReprojectRunService
from .recipes import (
    RecipeExecutionPreconditionError,
    RecipeExecutionResult,
    RecipeExecutionService,
)

__all__ = [
    "BatchExecutionError",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "DockerWorker",
    "DockerVectorReprojectWorker",
    "ExecutionPreconditionError",
    "ExecutionResult",
    "ImplementationRegistry",
    "ImplementationRegistryError",
    "ProcessedFeatureBatch",
    "RecipeExecutionPreconditionError",
    "RecipeExecutionResult",
    "RecipeExecutionService",
    "RemoteVectorBufferWorker",
    "RemoteVectorReprojectWorker",
    "RunRepository",
    "StreamingFinalizationResult",
    "StreamingRunFinalizer",
    "SpatialWorkerIdentity",
    "RunStateError",
    "VectorBufferBatchExecutor",
    "VectorBufferRunService",
    "VectorBufferWorker",
    "VectorReprojectRunService",
    "VectorReprojectWorker",
    "WorkerExecutionError",
    "WorkerResult",
    "WorkerTimeoutError",
    "WorkerUnavailableError",
]
