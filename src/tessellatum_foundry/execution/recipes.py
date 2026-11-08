"""Sequential execution of validated Recipe DAGs through immutable cell Runs."""

from __future__ import annotations

import uuid
from copy import deepcopy
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from tessellatum_foundry.execution.service import (
    ExecutionPreconditionError,
    ExecutionResult,
)
from tessellatum_foundry.execution.protocol import CellExecutionRunner
from tessellatum_foundry.execution.capabilities import CapabilityRegistryError
from tessellatum_foundry.execution.implementations import ImplementationRegistryError
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.definitions import (
    DefinitionIntegrityError,
    VersionedDefinitionStore,
)
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.graph import validate_recipe_graph
from tessellatum_foundry.validation.spatial import validate_recipe_spatial


class RecipeExecutionPreconditionError(ValueError):
    """Raised when a Recipe cannot be safely scheduled for local execution."""


@dataclass(frozen=True)
class RecipeExecutionResult:
    """Aggregate view of a sequential Recipe execution and its per-cell Runs."""

    execution_id: str
    recipe: dict[str, str]
    status: str
    node_results: dict[str, ExecutionResult]
    outputs: dict[str, dict[str, Any]]
    failed_node_id: str | None = None
    error: dict[str, Any] | None = None


class RecipeExecutionService:
    """Execute Recipe nodes sequentially while preserving their original declarations."""

    def __init__(
        self,
        *,
        cell_runner: CellExecutionRunner | None = None,
        cell_runners: dict[tuple[str, str], CellExecutionRunner] | None = None,
        artifact_store: FileSystemArtifactStore,
        contracts: ContractRegistry | None = None,
        definitions: VersionedDefinitionStore | None = None,
    ) -> None:
        self.cell_runners = dict(cell_runners or {})
        if cell_runner is not None:
            key = (
                cell_runner.worker.capability_id,
                cell_runner.worker.capability_version,
            )
            existing = self.cell_runners.get(key)
            if existing is not None and existing is not cell_runner:
                raise ValueError(
                    f"Multiple Cell runners are registered for {key[0]}@{key[1]}."
                )
            self.cell_runners[key] = cell_runner
        if not self.cell_runners:
            raise ValueError("At least one capability-specific Cell runner is required.")
        # Compatibility alias for callers that used the original single-runner API.
        self.cell_runner = cell_runner or next(iter(self.cell_runners.values()))
        self.artifact_store = artifact_store
        self.contracts = contracts or ContractRegistry()
        self.definitions = definitions

    def execute(
        self,
        *,
        recipe: dict[str, Any],
        cells: dict[tuple[str, str], dict[str, Any]],
        capabilities: dict[tuple[str, str], dict[str, Any]],
        actor_id: str,
    ) -> RecipeExecutionResult:
        recipe = deepcopy(recipe)
        cells = deepcopy(cells)
        capabilities = deepcopy(capabilities)
        self.contracts.validate("recipe.schema.json", recipe)
        referenced_cells = []

        for node in recipe["nodes"]:
            cell_ref = node["cell"]
            cell = cells.get((cell_ref["cell_id"], cell_ref["version"]))
            if cell is not None:
                self.contracts.validate("cell.schema.json", cell)
                referenced_cells.append(cell)
                capability_ref = cell["capability"]
                capability = capabilities.get(
                    (capability_ref["capability_id"], capability_ref["version"])
                )
                if capability is not None:
                    self.contracts.validate("capability.schema.json", capability)

        graph_findings = validate_recipe_graph(
            recipe,
            cells=cells,
            capabilities=capabilities,
        )
        if graph_findings:
            detail = "; ".join(
                f"{finding.code}: {finding.message}" for finding in graph_findings
            )
            raise RecipeExecutionPreconditionError(
                f"Recipe graph preconditions failed: {detail}"
            )

        recipe_cells = referenced_cells
        artifacts: dict[tuple[str, str], dict[str, Any]] = {}
        artifact_keys: set[tuple[str, str]] = set()
        for cell in recipe_cells:
            for binding in cell.get("inputs", {}).values():
                if binding["source"] != "artifact":
                    continue
                reference = binding["artifact"]
                key = (reference["artifact_id"], reference["version"])
                if key not in artifacts:
                    try:
                        artifacts[key] = self.artifact_store.get_artifact(*key)
                    except FileNotFoundError as error:
                        raise RecipeExecutionPreconditionError(
                            f"External Artifact {key[0]}@{key[1]} is not registered."
                        ) from error
                    artifact_keys.add(key)

        graph_findings = validate_recipe_graph(
            recipe,
            cells=cells,
            capabilities=capabilities,
            artifacts=artifact_keys,
        )
        if graph_findings:
            detail = "; ".join(
                f"{finding.code}: {finding.message}" for finding in graph_findings
            )
            raise RecipeExecutionPreconditionError(
                f"Recipe graph preconditions failed: {detail}"
            )

        spatial_findings = validate_recipe_spatial(
            recipe,
            cells=cells,
            capabilities=capabilities,
            artifacts=artifacts,
        )
        if spatial_findings:
            detail = "; ".join(
                f"{finding.code}: {finding.message}" for finding in spatial_findings
            )
            raise RecipeExecutionPreconditionError(
                f"Recipe spatial preconditions failed: {detail}"
            )

        configured_runners: set[int] = set()
        for node in recipe["nodes"]:
            cell_ref = node["cell"]
            cell = cells[(cell_ref["cell_id"], cell_ref["version"])]
            capability_ref = cell["capability"]
            capability = capabilities[
                (capability_ref["capability_id"], capability_ref["version"])
            ]
            runner = self._runner_for(
                capability_ref["capability_id"], capability_ref["version"]
            )
            if id(runner) not in configured_runners:
                try:
                    runner.validate_worker_configuration()
                except ExecutionPreconditionError as error:
                    raise RecipeExecutionPreconditionError(str(error)) from error
                configured_runners.add(id(runner))
            try:
                runner.capabilities.require_exact(capability)
            except CapabilityRegistryError as error:
                raise RecipeExecutionPreconditionError(str(error)) from error
            if (
                capability["capability_id"] != runner.worker.capability_id
                or capability["version"] != runner.worker.capability_version
            ):
                raise RecipeExecutionPreconditionError(
                    "Selected Cell runner does not support the exact Capability version."
                )
            try:
                runner.implementations.require_conformant(
                    implementation_id=runner.worker.implementation_id,
                    version=runner.worker.implementation_version,
                    capability_id=capability["capability_id"],
                    capability_version=capability["version"],
                )
            except ImplementationRegistryError as error:
                raise RecipeExecutionPreconditionError(str(error)) from error

        node_order = self._topological_order(recipe)
        node_by_cell = {
            (node["cell"]["cell_id"], node["cell"]["version"]): node["node_id"]
            for node in recipe["nodes"]
        }
        node_results: dict[str, ExecutionResult] = {}
        execution_id = f"recipe-execution:{uuid.uuid4().hex}"
        recipe_ref = {
            "recipe_id": recipe["recipe_id"],
            "version": recipe["version"],
        }
        runtime_image_digests: dict[int, str] = {}

        for node_order_index, node_id in enumerate(node_order):
            node = next(item for item in recipe["nodes"] if item["node_id"] == node_id)
            cell_ref = node["cell"]
            cell = cells[(cell_ref["cell_id"], cell_ref["version"])]
            capability_ref = cell["capability"]
            capability = capabilities[
                (capability_ref["capability_id"], capability_ref["version"])
            ]
            runner = self._runner_for(
                capability_ref["capability_id"], capability_ref["version"]
            )
            runner_key = id(runner)
            resolved_inputs: dict[str, dict[str, Any]] = {}
            for port_id, binding in cell.get("inputs", {}).items():
                if binding["source"] != "cell_output":
                    continue
                source_key = (binding["cell_id"], binding["cell_version"])
                source_node_id = node_by_cell[source_key]
                source_result = node_results[source_node_id]
                if source_result.run["status"] != "succeeded":
                    raise RecipeExecutionPreconditionError(
                        f"Upstream node {source_node_id!r} did not succeed."
                    )
                source_output = next(
                    (
                        output
                        for output in source_result.run.get("outputs", [])
                        if output["output_port"] == binding["output_port"]
                    ),
                    None,
                )
                if source_output is None:
                    raise RecipeExecutionPreconditionError(
                        f"Upstream node {source_node_id!r} did not produce "
                        f"output port {binding['output_port']!r}."
                    )
                resolved_inputs[port_id] = {
                    "source_run_id": source_result.run["run_id"],
                    "source_output_port": binding["output_port"],
                    "artifact": source_output["artifact"],
                }

            try:
                result = runner.execute(
                    cell=cell,
                    capability=capability,
                    actor_id=actor_id,
                    recipe_ref=recipe_ref,
                    recipe_execution_id=execution_id,
                    recipe_node_id=node_id,
                    recipe_node_order=node_order_index,
                    resolved_inputs=resolved_inputs,
                    pinned_runtime_image_digest=runtime_image_digests.get(runner_key),
                )
            except ExecutionPreconditionError as error:
                return RecipeExecutionResult(
                    execution_id=execution_id,
                    recipe=recipe_ref,
                    status="failed",
                    node_results=node_results,
                    outputs={},
                    failed_node_id=node_id,
                    error={"code": "execution.precondition_failed", "message": str(error)},
                )
            node_results[node_id] = result
            runtime_digest = result.run.get("runtime_image_digest")
            if runtime_digest is not None:
                runtime_image_digests.setdefault(runner_key, runtime_digest)
            if result.run["status"] != "succeeded":
                return RecipeExecutionResult(
                    execution_id=execution_id,
                    recipe=recipe_ref,
                    status="failed",
                    node_results=node_results,
                    outputs={},
                    failed_node_id=node_id,
                    error=result.run.get("error"),
                )

        declared_outputs: dict[str, dict[str, Any]] = {}
        for declaration in recipe.get("declared_outputs", []):
            node_result = node_results[declaration["node_id"]]
            output = next(
                (
                    item
                    for item in node_result.run.get("outputs", [])
                    if item["output_port"] == declaration["output_port"]
                ),
                None,
            )
            if output is None:
                raise RecipeExecutionPreconditionError(
                    f"Declared Recipe output {declaration['name']!r} was not produced."
                )
            artifact_ref = output["artifact"]
            declared_outputs[declaration["name"]] = self.artifact_store.get_artifact(
                artifact_ref["artifact_id"], artifact_ref["version"]
            )

        return RecipeExecutionResult(
            execution_id=execution_id,
            recipe=recipe_ref,
            status="succeeded",
            node_results=node_results,
            outputs=declared_outputs,
        )

    def execute_registered(
        self,
        *,
        recipe_id: str,
        version: str,
        actor_id: str,
    ) -> RecipeExecutionResult:
        """Resolve an immutable registered Recipe and execute its exact dependencies."""
        if self.definitions is None:
            raise RecipeExecutionPreconditionError(
                "No versioned definition store is configured."
            )
        try:
            recipe = self.definitions.get_recipe(recipe_id, version)
            cells: dict[tuple[str, str], dict[str, Any]] = {}
            capabilities: dict[tuple[str, str], dict[str, Any]] = {}
            for node in recipe["nodes"]:
                cell_ref = node["cell"]
                cell = self.definitions.get_cell(
                    cell_ref["cell_id"], cell_ref["version"]
                )
                cell_key = (cell["cell_id"], cell["version"])
                cells[cell_key] = cell
                capability_ref = cell["capability"]
                runner = self._runner_for(
                    capability_ref["capability_id"], capability_ref["version"]
                )
                capability = runner.capabilities.get(
                    capability_ref["capability_id"], capability_ref["version"]
                )
                capability_key = (
                    capability["capability_id"],
                    capability["version"],
                )
                capabilities[capability_key] = capability
        except (FileNotFoundError, DefinitionIntegrityError, CapabilityRegistryError) as error:
            raise RecipeExecutionPreconditionError(str(error)) from error

        return self.execute(
            recipe=recipe,
            cells=cells,
            capabilities=capabilities,
            actor_id=actor_id,
        )

    def _runner_for(self, capability_id: str, version: str) -> CellExecutionRunner:
        """Resolve the runner registered for one exact Capability version."""
        key = (capability_id, version)
        runner = self.cell_runners.get(key)
        if runner is None:
            raise RecipeExecutionPreconditionError(
                f"No Cell runner is registered for Capability {capability_id}@{version}."
            )
        return runner

    @staticmethod
    def _topological_order(recipe: dict[str, Any]) -> list[str]:
        node_ids = [node["node_id"] for node in recipe["nodes"]]
        adjacency: dict[str, set[str]] = defaultdict(set)
        indegree = dict.fromkeys(node_ids, 0)
        for edge in recipe.get("edges", []):
            source = edge["from"]["node_id"]
            target = edge["to"]["node_id"]
            if target not in adjacency[source]:
                adjacency[source].add(target)
                indegree[target] += 1

        ready = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
        ordered: list[str] = []
        while ready:
            node_id = ready.popleft()
            ordered.append(node_id)
            for downstream in sorted(adjacency[node_id]):
                indegree[downstream] -= 1
                if indegree[downstream] == 0:
                    ready.append(downstream)

        if len(ordered) != len(node_ids):
            raise RecipeExecutionPreconditionError(
                "Recipe dependencies contain a directed cycle."
            )
        return ordered
