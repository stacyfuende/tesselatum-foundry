"""Run lifecycle integration for the vector.reproject capability."""

from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from typing import Any

from shapely.geometry import shape

from tessellatum_foundry.capabilities.buffer_contract import resolve_crs
from tessellatum_foundry.capabilities.vector_reproject import (
    ReprojectContractError,
    validate_reproject_request,
)
from tessellatum_foundry.execution.docker_worker import (
    WorkerExecutionError,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from tessellatum_foundry.execution.capabilities import CapabilityRegistryError
from tessellatum_foundry.execution.implementations import ImplementationRegistryError
from tessellatum_foundry.execution.protocol import VectorReprojectWorker
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import (
    ExecutionPreconditionError,
    ExecutionResult,
    VectorBufferRunService,
)
from tessellatum_foundry.storage.artifacts import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    utc_timestamp,
)
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.output import inspect_vector_reproject_output


class VectorReprojectRunService(VectorBufferRunService):
    """Execute one exact vector.reproject Cell and persist independently checked evidence."""

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
        worker: VectorReprojectWorker,
        contracts: ContractRegistry | None = None,
        implementations=None,
        capabilities=None,
    ) -> None:
        super().__init__(
            artifact_store=artifact_store,
            run_repository=run_repository,
            worker=worker,  # type: ignore[arg-type]
            contracts=contracts,
            implementations=implementations,
            capabilities=capabilities,
        )

    def execute(
        self,
        *,
        cell: dict[str, Any],
        capability: dict[str, Any],
        actor_id: str,
        retry_of_run_id: str | None = None,
        recipe_ref: dict[str, str] | None = None,
        recipe_execution_id: str | None = None,
        recipe_node_id: str | None = None,
        recipe_node_order: int | None = None,
        resolved_inputs: dict[str, dict[str, Any]] | None = None,
        pinned_runtime_image_digest: str | None = None,
    ) -> ExecutionResult:
        cell = deepcopy(cell)
        capability = deepcopy(capability)
        recipe_ref = deepcopy(recipe_ref)
        resolved_inputs = deepcopy(resolved_inputs or {})
        self.contracts.validate("cell.schema.json", cell)
        self.contracts.validate("capability.schema.json", capability)
        try:
            capability = self.capabilities.require_exact(capability)
        except CapabilityRegistryError as error:
            raise ExecutionPreconditionError(str(error)) from error
        if capability.get("capability_id") != "vector.reproject":
            raise ExecutionPreconditionError(
                "This Run service only supports vector.reproject."
            )
        if (
            self.worker.capability_id != "vector.reproject"
            or self.worker.capability_version != capability["version"]
        ):
            raise ExecutionPreconditionError(
                "Selected worker does not implement the exact supplied Capability version."
            )
        self.validate_worker_configuration()
        recipe_context = (
            recipe_ref,
            recipe_execution_id,
            recipe_node_id,
            recipe_node_order,
        )
        if any(value is None for value in recipe_context) and any(
            value is not None for value in recipe_context
        ):
            raise ExecutionPreconditionError(
                "Recipe reference, execution ID, node ID, and node order must be supplied together."
            )
        if recipe_node_order is not None and (
            not isinstance(recipe_node_order, int)
            or isinstance(recipe_node_order, bool)
            or recipe_node_order < 0
        ):
            raise ExecutionPreconditionError(
                "Recipe node order must be a non-negative integer."
            )
        if recipe_node_id is not None and (
            not isinstance(recipe_node_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}", recipe_node_id)
        ):
            raise ExecutionPreconditionError("Recipe node ID must be a valid identifier.")
        if pinned_runtime_image_digest is not None and (
            not isinstance(pinned_runtime_image_digest, str)
            or not re.fullmatch(
                r"sha256:[a-fA-F0-9]{64}", pinned_runtime_image_digest
            )
        ):
            raise ExecutionPreconditionError(
                "Pinned runtime image digest must be an immutable SHA-256 image ID."
            )
        try:
            implementation_manifest = self.implementations.require_conformant(
                implementation_id=self.worker.implementation_id,
                version=self.worker.implementation_version,
                capability_id=capability["capability_id"],
                capability_version=capability["version"],
            )
        except ImplementationRegistryError as error:
            raise ExecutionPreconditionError(str(error)) from error
        if cell["capability"] != {
            "capability_id": capability["capability_id"],
            "version": capability["version"],
        }:
            raise ExecutionPreconditionError(
                "Geo-Cell capability reference does not match the supplied contract."
            )

        parameters = self._normalize_parameters(cell, capability)
        input_port = self._required_port(capability["input_ports"], "features")
        output_port = self._required_port(capability["output_ports"], "result")
        output_contract = cell["output_contracts"].get("result")
        if output_contract is None or output_contract.get("crs") is None:
            raise ExecutionPreconditionError(
                "Geo-Cell result output must declare its target CRS."
            )
        output_media_type = self._output_media_type(output_contract, output_port)
        permitted_geometry_types = set(
            output_contract.get("geometry_types", [])
        ).intersection(output_port.get("spatial", {}).get("geometry_types", []))
        if not permitted_geometry_types:
            raise ExecutionPreconditionError(
                "Geo-Cell and capability do not declare compatible output geometry types."
            )
        try:
            target_crs = resolve_crs(parameters["target_crs"], "Target CRS")
            declared_output_crs = resolve_crs(output_contract["crs"], "Output contract CRS")
        except Exception as error:
            raise ExecutionPreconditionError(str(error)) from error
        if not target_crs.equals(declared_output_crs, ignore_axis_order=True):
            raise ExecutionPreconditionError(
                "Cell target_crs parameter must equal its declared output contract CRS."
            )

        binding = cell.get("inputs", {}).get("features")
        if not isinstance(binding, dict):
            raise ExecutionPreconditionError("Required features input is not bound.")
        lineage: dict[str, str] = {}
        if binding.get("source") == "artifact":
            if resolved_inputs:
                raise ExecutionPreconditionError(
                    "Resolved upstream inputs were supplied for an Artifact-bound cell."
                )
            artifact_ref = binding["artifact"]
        elif binding.get("source") == "cell_output":
            if recipe_ref is None or recipe_execution_id is None:
                raise ExecutionPreconditionError(
                    "A cell-output binding can only execute within a Recipe execution."
                )
            resolution = resolved_inputs.get("features")
            if not isinstance(resolution, dict):
                raise ExecutionPreconditionError(
                    "The upstream cell-output binding has not been resolved."
                )
            source_run_id = resolution.get("source_run_id")
            source_output_port = resolution.get("source_output_port")
            artifact_ref = resolution.get("artifact")
            if (
                not isinstance(source_run_id, str)
                or not isinstance(source_output_port, str)
                or not isinstance(artifact_ref, dict)
            ):
                raise ExecutionPreconditionError(
                    "Resolved upstream input must identify its source Run, output port, "
                    "and Artifact."
                )
            source_run = self.run_repository.get_run(source_run_id)
            if source_run["status"] != "succeeded":
                raise ExecutionPreconditionError("Upstream Run must have succeeded.")
            if (
                source_run.get("recipe_execution_id") != recipe_execution_id
                or source_run.get("recipe") != recipe_ref
            ):
                raise ExecutionPreconditionError(
                    "Upstream Run must belong to this exact Recipe execution."
                )
            if source_run["cell"] != {
                "cell_id": binding["cell_id"],
                "version": binding["cell_version"],
            }:
                raise ExecutionPreconditionError(
                    "Upstream Run does not belong to the exact cell version in the binding."
                )
            if source_output_port != binding["output_port"]:
                raise ExecutionPreconditionError(
                    "Resolved upstream output port differs from the cell binding."
                )
            produced = any(
                output.get("output_port") == source_output_port
                and output.get("artifact") == artifact_ref
                for output in source_run.get("outputs", [])
            )
            if not produced:
                raise ExecutionPreconditionError(
                    "Upstream Run did not produce the resolved Artifact on that output port."
                )
            lineage = {
                "source_run_id": source_run_id,
                "source_output_port": source_output_port,
            }
        else:
            raise ExecutionPreconditionError("Unsupported features input binding source.")
        if set(resolved_inputs) - {"features"}:
            raise ExecutionPreconditionError(
                "Resolved inputs contain ports not declared by this execution service."
            )
        try:
            input_artifact = self.artifact_store.get_artifact(
                artifact_ref["artifact_id"], artifact_ref["version"]
            )
        except FileNotFoundError as error:
            raise ExecutionPreconditionError(
                "Resolved input Artifact is not registered."
            ) from error
        if input_artifact["media_type"] not in input_port.get("accepted_media_types", []):
            raise ExecutionPreconditionError(
                "Input Artifact media type is not accepted by the capability contract."
            )
        if input_artifact.get("spatial", {}).get("kind") != "vector":
            raise ExecutionPreconditionError("Input Artifact must contain vector data.")
        input_crs = input_artifact.get("spatial", {}).get("crs")
        if not input_crs:
            raise ExecutionPreconditionError("Input vector Artifact must declare its CRS.")
        try:
            input_bytes = self.artifact_store.read_bytes(input_artifact)
        except ArtifactIntegrityError as error:
            raise ExecutionPreconditionError(
                f"Input Artifact failed checksum verification: {error}"
            ) from error
        try:
            input_feature_collection = json.loads(input_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExecutionPreconditionError(
                "Input Artifact does not contain valid UTF-8 JSON."
            ) from error
        if not isinstance(input_feature_collection, dict):
            raise ExecutionPreconditionError("Input Artifact JSON must be an object.")

        self._validate_spatial_declarations(
            cell=cell,
            capability=capability,
            resolved_artifacts={"features": input_artifact},
        )
        try:
            validate_reproject_request(
                input_feature_collection,
                input_crs=input_crs,
                target_crs=parameters["target_crs"],
            )
        except ReprojectContractError as error:
            raise ExecutionPreconditionError(
                f"Input data does not satisfy vector.reproject preconditions: {error}"
            ) from error

        actual_geometry_types = {
            shape(feature["geometry"]).geom_type
            for feature in input_feature_collection["features"]
        }
        declared_geometry_types = set(
            input_artifact.get("spatial", {}).get("geometry_types", [])
        )
        if actual_geometry_types != declared_geometry_types:
            raise ExecutionPreconditionError(
                "Input Artifact geometry_types metadata does not match its feature data."
            )
        if not actual_geometry_types.issubset(permitted_geometry_types):
            raise ExecutionPreconditionError(
                "Output contract does not permit all input geometry types."
            )

        input_snapshot = {
            "input_port": "features",
            "artifact": artifact_ref,
            "checksum": input_artifact["checksum"]["value"],
            **lineage,
        }
        attempt = 1
        if retry_of_run_id is not None:
            previous = self.run_repository.get_run(retry_of_run_id)
            if previous["status"] not in {"failed", "timed_out"}:
                raise ExecutionPreconditionError(
                    "Only failed or timed-out Runs can be retried."
                )
            if not previous.get("error", {}).get("retryable", False):
                raise ExecutionPreconditionError(
                    "The previous Run is not marked as retryable."
                )
            if previous["cell"] != {
                "cell_id": cell["cell_id"],
                "version": cell["version"],
            }:
                raise ExecutionPreconditionError("A retry must use the same Geo-Cell version.")
            if previous["capability"] != {
                "capability_id": capability["capability_id"],
                "version": capability["version"],
            }:
                raise ExecutionPreconditionError("A retry must use the same Capability version.")
            if (
                previous.get("recipe") != recipe_ref
                or previous.get("recipe_execution_id") != recipe_execution_id
                or previous.get("recipe_node_id") != recipe_node_id
                or previous.get("recipe_node_order") != recipe_node_order
            ):
                raise ExecutionPreconditionError(
                    "A retry must preserve the original Recipe execution context."
                )
            if previous.get("input_snapshots") != [input_snapshot]:
                raise ExecutionPreconditionError("A retry must use the same immutable inputs.")
            if previous.get("normalized_parameters") != parameters:
                raise ExecutionPreconditionError("A retry must use the same normalized parameters.")
            attempt = previous["attempt"] + 1

        run_id = f"run:{uuid.uuid4().hex}"
        self.run_repository.create_queued_run(
            run_id=run_id,
            cell={"cell_id": cell["cell_id"], "version": cell["version"]},
            capability={
                "capability_id": capability["capability_id"],
                "version": capability["version"],
            },
            input_snapshots=[input_snapshot],
            normalized_parameters=parameters,
            attempt=attempt,
            retry_of_run_id=retry_of_run_id,
            recipe=recipe_ref,
            recipe_execution_id=recipe_execution_id,
            recipe_node_id=recipe_node_id,
            recipe_node_order=recipe_node_order,
        )

        try:
            image_digest = pinned_runtime_image_digest or self.worker.image_digest()
            if not isinstance(image_digest, str) or not re.fullmatch(
                r"sha256:[a-fA-F0-9]{64}", image_digest
            ):
                raise WorkerUnavailableError(
                    "Worker returned an invalid immutable runtime image digest."
                )
        except WorkerUnavailableError as error:
            failed = self.run_repository.transition(
                run_id,
                expected_status="queued",
                new_status="failed",
                fields={
                    "finished_at": utc_timestamp(),
                    "error": {
                        "code": "worker.unavailable",
                        "message": str(error),
                        "retryable": True,
                    },
                },
                event_type="worker_unavailable",
            )
            return ExecutionResult(failed, None, None)

        manifest_checksum = self.implementations.manifest_checksum(
            implementation_manifest["implementation_id"],
            implementation_manifest["version"],
        )
        cache_record = self._cache_record(
            cell=cell,
            capability=capability,
            parameters=parameters,
            input_snapshot=input_snapshot,
            implementation=implementation_manifest,
            manifest_checksum=manifest_checksum,
            runtime_image_digest=image_digest,
        )
        cache_reuse = self._find_cache_reuse(
            cache_record=cache_record,
            input_artifact=input_artifact,
            output_media_type=output_media_type,
            output_contract=output_contract,
            permitted_geometry_types=permitted_geometry_types,
        )
        if cache_reuse is not None:
            cache_record = {
                **cache_record,
                "status": "hit",
                "source_run_id": cache_reuse["source_run"]["run_id"],
            }

        self.run_repository.transition(
            run_id,
            expected_status="queued",
            new_status="running",
            fields={
                "started_at": utc_timestamp(),
                "worker": {
                    "worker_id": self.worker.worker_id,
                    "worker_type": self.worker.worker_type,
                },
                "implementation": {
                    "implementation_id": implementation_manifest["implementation_id"],
                    "version": implementation_manifest["version"],
                    "manifest_checksum": manifest_checksum,
                },
                "runtime_image_digest": image_digest,
                "cache": cache_record,
            },
            event_type="cache_hit" if cache_reuse is not None else "worker_started",
            event_detail=(
                {"source_run_id": cache_record["source_run_id"]}
                if cache_reuse is not None
                else {"runtime_image_digest": image_digest}
            ),
        )

        if cache_reuse is not None:
            report = self._cache_reuse_report(
                run_id=run_id,
                source_run=cache_reuse["source_run"],
                source_report=cache_reuse["source_report"],
                artifact=cache_reuse["artifact"],
            )
            self.run_repository.save_validation_report(report)
            finished = self.run_repository.transition(
                run_id,
                expected_status="running",
                new_status="succeeded",
                fields={
                    "finished_at": utc_timestamp(),
                    "outputs": [
                        {
                            "output_port": "result",
                            "artifact": {
                                "artifact_id": cache_reuse["artifact"]["artifact_id"],
                                "version": cache_reuse["artifact"]["version"],
                            },
                        }
                    ],
                    "validation_report_ids": [report["report_id"]],
                    "resource_usage": {"duration_ms": 0},
                },
                event_type="run_succeeded_from_cache",
                event_detail={"source_run_id": cache_record["source_run_id"]},
            )
            return ExecutionResult(finished, cache_reuse["artifact"], report)

        try:
            result = self.worker.execute(
                input_bytes=input_bytes,
                capability_version=capability["version"],
                input_crs=input_crs,
                target_crs=parameters["target_crs"],
                parameters=parameters,
                runtime_image_digest=image_digest,
            )
            if result.runtime_image_digest != image_digest:
                raise WorkerExecutionError(
                    "Worker result image digest differs from the pinned execution image."
                )
            inspection = inspect_vector_reproject_output(
                input_feature_collection=input_feature_collection,
                output_feature_collection=result.feature_collection,
                expected_output_crs=output_contract["crs"],
                actual_output_crs=result.crs,
                permitted_geometry_types=permitted_geometry_types,
            )
            report = self._output_report(run_id, inspection)
            report["validator"] = {
                "name": "foundry-spatial-output-critic",
                "version": "0.2.0",
            }
            self.run_repository.save_validation_report(report)
            if not inspection.passed:
                failed = self.run_repository.transition(
                    run_id,
                    expected_status="running",
                    new_status="failed",
                    fields={
                        "finished_at": utc_timestamp(),
                        "validation_report_ids": [report["report_id"]],
                        "error": {
                            "code": "output.validation_failed",
                            "message": "Output did not satisfy the declared output contract.",
                            "retryable": False,
                        },
                    },
                    event_type="output_validation_failed",
                )
                return ExecutionResult(failed, None, report)

            output_spatial = {
                "kind": "vector",
                "crs": output_contract["crs"],
                "geometry_types": list(inspection.geometry_types),
            }
            output_bytes = json.dumps(
                result.feature_collection,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            output_artifact = self.artifact_store.put_bytes(
                artifact_id=f"artifact:{run_id}:result",
                version="1.0.0",
                content=output_bytes,
                created_by=actor_id,
                media_type=output_media_type,
                format_name="Foundry Spatial Feature Collection JSON",
                spatial=output_spatial,
                rights=input_artifact.get("rights"),
                metadata={
                    "producer_run_id": run_id,
                    "output_port": "result",
                },
            )
            finished = self.run_repository.transition(
                run_id,
                expected_status="running",
                new_status="succeeded",
                fields={
                    "finished_at": utc_timestamp(),
                    "outputs": [
                        {
                            "output_port": "result",
                            "artifact": {
                                "artifact_id": output_artifact["artifact_id"],
                                "version": output_artifact["version"],
                            },
                        }
                    ],
                    "validation_report_ids": [report["report_id"]],
                    "resource_usage": {"duration_ms": result.duration_ms},
                },
                event_type="run_succeeded",
            )
            return ExecutionResult(finished, output_artifact, report)
        except WorkerTimeoutError as error:
            terminal_status = "timed_out"
            error_code = "worker.timeout"
            retryable = True
            failure_message = str(error)
        except (WorkerExecutionError, WorkerUnavailableError) as error:
            terminal_status = "failed"
            error_code = "worker.execution_failed"
            retryable = isinstance(error, WorkerUnavailableError)
            failure_message = str(error)
        except Exception as error:
            terminal_status = "failed"
            error_code = "execution.internal_error"
            retryable = False
            failure_message = f"{type(error).__name__}: {error}"

        failed = self.run_repository.transition(
            run_id,
            expected_status="running",
            new_status=terminal_status,
            fields={
                "finished_at": utc_timestamp(),
                "error": {
                    "code": error_code,
                    "message": failure_message,
                    "retryable": retryable,
                },
            },
            event_type=terminal_status,
        )
        return ExecutionResult(failed, None, None)
