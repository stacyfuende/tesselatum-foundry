"""Small local Python SDK facade over the canonical Foundry contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.docker_worker import (
    DockerVectorReprojectWorker,
    DockerWorker,
)
from tessellatum_foundry.execution.implementations import ImplementationRegistry
from tessellatum_foundry.execution.protocol import (
    VectorBufferWorker,
    VectorReprojectWorker,
)
from tessellatum_foundry.execution.recipes import (
    RecipeExecutionResult,
    RecipeExecutionService,
)
from tessellatum_foundry.execution.reproject_service import VectorReprojectRunService
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import VectorBufferRunService
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.definitions import VersionedDefinitionStore
from tessellatum_foundry.validation.contracts import ContractRegistry


class LocalFoundry:
    """Compose local control-plane services for the registered vector capabilities.

    This is a local SDK adapter, not a network API or multi-tenant service.
    Persistent data is written beneath the caller-supplied root directory.
    """

    def __init__(
        self,
        root: Path,
        *,
        worker: VectorBufferWorker | None = None,
        reproject_worker: VectorReprojectWorker | None = None,
        contracts: ContractRegistry | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.contracts = contracts or ContractRegistry()
        self.artifacts = FileSystemArtifactStore(
            self.root / "artifacts", self.contracts
        )
        self.runs = RunRepository(self.root / "control", self.contracts)
        self.definitions = VersionedDefinitionStore(
            self.root / "definitions", self.contracts
        )
        self.capabilities = CapabilityRegistry(contracts=self.contracts)
        self.implementations = ImplementationRegistry(contracts=self.contracts)

        # Preserve the original worker argument and cell_runner alias for callers
        # that configured the v0.1 vector.buffer-only SDK.
        self.worker = worker if worker is not None else DockerWorker()
        self.reproject_worker = (
            reproject_worker
            if reproject_worker is not None
            else DockerVectorReprojectWorker()
        )
        self.cell_runner = VectorBufferRunService(
            artifact_store=self.artifacts,
            run_repository=self.runs,
            worker=self.worker,
            contracts=self.contracts,
            capabilities=self.capabilities,
            implementations=self.implementations,
        )
        self.reproject_runner = VectorReprojectRunService(
            artifact_store=self.artifacts,
            run_repository=self.runs,
            worker=self.reproject_worker,
            contracts=self.contracts,
            capabilities=self.capabilities,
            implementations=self.implementations,
        )
        self.cell_runners = {
            ("vector.buffer", "1.0.0"): self.cell_runner,
            ("vector.reproject", "1.0.0"): self.reproject_runner,
        }
        self.recipes = RecipeExecutionService(
            cell_runners=self.cell_runners,
            artifact_store=self.artifacts,
            contracts=self.contracts,
            definitions=self.definitions,
        )

    def register_cell(
        self, cell: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        """Validate and immutably register one exact Geo-Cell version."""
        return self.definitions.put_cell(cell, created_by=created_by)

    def register_recipe(
        self, recipe: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        """Validate and immutably register one exact Recipe version."""
        return self.definitions.put_recipe(recipe, created_by=created_by)

    def execute_recipe(
        self, *, recipe_id: str, version: str, actor_id: str
    ) -> RecipeExecutionResult:
        """Execute an exact registered Recipe version."""
        return self.recipes.execute_registered(
            recipe_id=recipe_id,
            version=version,
            actor_id=actor_id,
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Retrieve a persisted Run by its exact ID."""
        return self.runs.get_run(run_id)

    def list_recipe_runs(self, recipe_execution_id: str) -> list[dict[str, Any]]:
        """List per-cell Runs for one Recipe execution in node order."""
        return self.runs.list_runs_for_recipe_execution(recipe_execution_id)

    def store_artifact(
        self,
        *,
        artifact_id: str,
        version: str,
        content: bytes,
        created_by: str,
        media_type: str,
        format_name: str,
        spatial: dict[str, Any] | None = None,
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register an immutable Artifact version and its metadata."""
        return self.artifacts.put_bytes(
            artifact_id=artifact_id,
            version=version,
            content=content,
            created_by=created_by,
            media_type=media_type,
            format_name=format_name,
            spatial=spatial,
            rights=rights,
            metadata=metadata,
        )

    def get_artifact(self, artifact_id: str, version: str) -> dict[str, Any]:
        """Retrieve immutable Artifact metadata."""
        return self.artifacts.get_artifact(artifact_id, version)

    def get_validation_report(self, report_id: str) -> dict[str, Any]:
        """Retrieve persisted validation evidence for an exact report ID."""
        return self.runs.get_validation_report(report_id)

    def read_artifact(self, artifact: dict[str, Any]) -> bytes:
        """Read and checksum-verify the bytes of a registered Artifact."""
        return self.artifacts.read_bytes(artifact)
