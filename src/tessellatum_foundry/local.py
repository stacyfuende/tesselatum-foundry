"""Small local Python SDK facade over the canonical Foundry contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.docker_worker import DockerWorker
from tessellatum_foundry.execution.implementations import ImplementationRegistry
from tessellatum_foundry.execution.protocol import VectorBufferWorker
from tessellatum_foundry.execution.recipes import (
    RecipeExecutionResult,
    RecipeExecutionService,
)
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import VectorBufferRunService
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.definitions import VersionedDefinitionStore
from tessellatum_foundry.validation.contracts import ContractRegistry


class LocalFoundry:
    """Compose the local control plane and expose a compact Python entrypoint.

    This is a local SDK adapter, not a network API or multi-tenant service.
    Persistent data is written beneath the caller-supplied root directory.
    """

    def __init__(
        self,
        root: Path,
        *,
        worker: VectorBufferWorker | None = None,
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
        self.worker = worker or DockerWorker()
        self.cell_runner = VectorBufferRunService(
            artifact_store=self.artifacts,
            run_repository=self.runs,
            worker=self.worker,
            contracts=self.contracts,
            capabilities=self.capabilities,
            implementations=self.implementations,
        )
        self.recipes = RecipeExecutionService(
            cell_runner=self.cell_runner,
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

    def get_artifact(self, artifact_id: str, version: str) -> dict[str, Any]:
        """Retrieve immutable Artifact metadata."""
        return self.artifacts.get_artifact(artifact_id, version)

    def read_artifact(self, artifact: dict[str, Any]) -> bytes:
        """Read and checksum-verify the bytes of a registered Artifact."""
        return self.artifacts.read_bytes(artifact)
