"""Foundry execution orchestration and Run lifecycle components."""

from .autonomy import AutonomyPolicyError, evaluate_autonomy
from .product_blueprints import ProductBlueprintPlanError, plan_product_blueprint
from .product_delivery import ProductExportError, build_geojson_product_bundle
from .product_acceptance import (
    assemble_product_manifest,
    evaluate_product_acceptance,
)
from .product_execution import (
    ProductExecutionPreconditionError,
    compile_product_blueprint_recipe,
    execute_product_blueprint_plan,
)
from .experiments import (
    ExperimentExecutionError,
    ExperimentPlanError,
    execute_experiment,
    plan_experiment,
)
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
from .external_runs import ExternalVectorBufferRunFactory
from .external_orchestration import (
    ExternalRunAuthorizationError,
    ExternalVectorBufferRunOrchestrator,
)
from .streaming import StreamingFinalizationResult, StreamingRunFinalizer
from .streaming_pipeline import StreamingExecutionResult, StreamingVectorBufferPipeline
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
    "AutonomyPolicyError",
    "ProductExportError",
    "build_geojson_product_bundle",
    "ProductBlueprintPlanError",
    "assemble_product_manifest",
    "evaluate_product_acceptance",
    "ProductExecutionPreconditionError",
    "compile_product_blueprint_recipe",
    "execute_product_blueprint_plan",
    "plan_product_blueprint",
    "evaluate_autonomy",
    "BatchExecutionError",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "DockerWorker",
    "DockerVectorReprojectWorker",
    "ExecutionPreconditionError",
    "ExecutionResult",
    "ExperimentExecutionError",
    "ExperimentPlanError",
    "execute_experiment",
    "plan_experiment",
    "ExternalRunAuthorizationError",
    "ExternalVectorBufferRunFactory",
    "ExternalVectorBufferRunOrchestrator",
    "ImplementationRegistry",
    "ImplementationRegistryError",
    "ProcessedFeatureBatch",
    "RecipeExecutionPreconditionError",
    "RecipeExecutionResult",
    "RecipeExecutionService",
    "RemoteVectorBufferWorker",
    "RemoteVectorReprojectWorker",
    "RunRepository",
    "StreamingExecutionResult",
    "StreamingFinalizationResult",
    "StreamingRunFinalizer",
    "StreamingVectorBufferPipeline",
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
    "ExternalRasterWindowRunOrchestrator",
]

from tessellatum_foundry.execution.external_raster_orchestration import (
    ExternalRasterWindowRunOrchestrator,
)
