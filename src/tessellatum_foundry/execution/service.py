"""Single-cell vector.buffer execution through a local Docker worker."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from tessellatum_foundry.capabilities.buffer_contract import (
    BufferContractError,
    prepare_buffer_request,
)

from tessellatum_foundry.execution.docker_worker import (
    WorkerExecutionError,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from tessellatum_foundry.execution.capabilities import (
    CapabilityRegistry,
    CapabilityRegistryError,
)
from tessellatum_foundry.execution.implementations import (
    ImplementationRegistry,
    ImplementationRegistryError,
)
from tessellatum_foundry.execution.protocol import VectorBufferWorker
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.storage.artifacts import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    utc_timestamp,
)
from tessellatum_foundry.validation.contracts import (
    ContractRegistry,
    ContractValidationError,
)
from tessellatum_foundry.validation.output import inspect_vector_buffer_output
from tessellatum_foundry.validation.rights import build_rights_provenance_report
from tessellatum_foundry.validation.methodology import (
    build_methodology_report,
    coordinate_operation_evidence_valid,
)
from tessellatum_foundry.validation.spatial import validate_recipe_spatial


_OUTPUT_VALIDATOR_NAME = "foundry-spatial-output-critic"
_OUTPUT_VALIDATOR_VERSION = "0.2.0"
_REQUIRED_OUTPUT_CRS_FINDINGS = {
    "output.crs_matches_input",
    "output.crs_matches_contract",
}
_REQUIRED_OUTPUT_FINDINGS = {
    "output.feature_collection",
    "output.feature_count_preserved",
    "output.geometry_validity",
    "output.geometry_types",
    "output.coordinate_finiteness",
    "output.dimensionality",
    "output.feature_metadata",
}
_REQUIRED_OUTPUT_DIMENSIONS = {
    "feature_count",
    "feature_metadata",
    "crs",
    "geometry_type",
    "geometry_validity",
    "coordinate_finiteness",
    "dimensionality",
}


class ExecutionPreconditionError(ValueError):
    """Raised before a Run starts when its declarations are not executable."""


@dataclass(frozen=True)
class ExecutionResult:
    run: dict[str, Any]
    output_artifact: dict[str, Any] | None
    validation_report: dict[str, Any] | None


class VectorBufferRunService:
    """Execute one immutable Geo-Cell version and persist Run/output evidence."""

    MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
        worker: VectorBufferWorker,
        contracts: ContractRegistry | None = None,
        implementations: ImplementationRegistry | None = None,
        capabilities: CapabilityRegistry | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_repository = run_repository
        self.worker = worker
        self.contracts = contracts or ContractRegistry()
        self.implementations = implementations or ImplementationRegistry(
            contracts=self.contracts
        )
        self.capabilities = capabilities or CapabilityRegistry(
            contracts=self.contracts
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
        source_references: list[dict[str, Any]] | None = None,
        pinned_runtime_image_digest: str | None = None,
    ) -> ExecutionResult:
        cell = deepcopy(cell)
        capability = deepcopy(capability)
        recipe_ref = deepcopy(recipe_ref)
        resolved_inputs = deepcopy(resolved_inputs or {})
        source_references = (
            deepcopy(source_references) if source_references is not None else []
        )
        if not isinstance(source_references, list):
            raise ExecutionPreconditionError("Source references must be supplied as a list.")
        self.contracts.validate("cell.schema.json", cell)
        self.contracts.validate("capability.schema.json", capability)
        try:
            capability = self.capabilities.require_exact(capability)
        except CapabilityRegistryError as error:
            raise ExecutionPreconditionError(str(error)) from error
        if capability.get("capability_id") != "vector.buffer":
            raise ExecutionPreconditionError("This execution service only supports vector.buffer.")
        if (
            self.worker.capability_id != capability["capability_id"]
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
        seen_source_references: set[tuple[str, str, str, str | None]] = set()
        for source_entry in source_references:
            if not isinstance(source_entry, dict) or set(source_entry) != {
                "input_port", "reference"
            }:
                raise ExecutionPreconditionError(
                    "Each source reference must contain only input_port and reference."
                )
            if source_entry["input_port"] != input_port["port_id"]:
                raise ExecutionPreconditionError(
                    "External source evidence must identify a declared input port."
                )
            try:
                self.contracts.validate(
                    "external-data-reference.schema.json", source_entry["reference"]
                )
            except ContractValidationError as error:
                raise ExecutionPreconditionError(
                    f"External source reference is invalid: {error}"
                ) from error
            reference = source_entry["reference"]
            parsed_uri = urlsplit(reference["uri"])
            if (
                parsed_uri.username is not None
                or parsed_uri.password is not None
                or parsed_uri.query
                or parsed_uri.fragment
            ):
                raise ExecutionPreconditionError(
                    "External source reference is invalid: credentials, query parameters, "
                    "and fragments must not be embedded in the persisted URI."
                )
            identity = (
                source_entry["input_port"],
                reference["provider"],
                reference["dataset_id"],
                reference.get("resource_id"),
            )
            if identity in seen_source_references:
                raise ExecutionPreconditionError("Duplicate external source reference.")
            seen_source_references.add(identity)
        output_port = self._required_port(capability["output_ports"], "result")
        output_contract = cell["output_contracts"].get("result")
        if output_contract is None:
            raise ExecutionPreconditionError("Geo-Cell has no result output contract.")
        output_media_type = self._output_media_type(output_contract, output_port)
        permitted_geometry_types = set(
            output_contract.get("geometry_types", [])
        ).intersection(output_port.get("spatial", {}).get("geometry_types", []))
        if not permitted_geometry_types:
            raise ExecutionPreconditionError(
                "Geo-Cell and capability do not declare a compatible output geometry type."
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
        accepted_media_types = input_port.get("accepted_media_types", [])
        if input_artifact["media_type"] not in accepted_media_types:
            raise ExecutionPreconditionError(
                "Input Artifact media type is not accepted by the capability contract."
            )
        if input_artifact.get("spatial", {}).get("kind") != "vector":
            raise ExecutionPreconditionError("Input Artifact must contain vector data.")
        if not input_artifact.get("spatial", {}).get("crs"):
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
            prepared_input = prepare_buffer_request(
                input_feature_collection,
                input_crs=input_artifact["spatial"]["crs"],
                measurement_crs=cell["constraints"]["measurement_crs"],
                **parameters,
            )
        except BufferContractError as error:
            raise ExecutionPreconditionError(
                f"Input data does not satisfy vector.buffer preconditions: {error}"
            ) from error
        declared_geometry_types = set(
            input_artifact["spatial"].get("geometry_types", [])
        )
        actual_geometry_types = {
            feature.geometry_type for feature in prepared_input.features
        }
        if actual_geometry_types != declared_geometry_types:
            raise ExecutionPreconditionError(
                "Input Artifact geometry_types metadata does not match its feature data."
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
            if previous.get("source_references", []) != source_references:
                raise ExecutionPreconditionError(
                    "A retry must preserve the original external source evidence."
                )
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
            source_references=source_references,
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

        started_at = utc_timestamp()
        self.run_repository.transition(
            run_id,
            expected_status="queued",
            new_status="running",
            fields={
                "started_at": started_at,
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
            rights_report = build_rights_provenance_report(
                run_id=run_id,
                input_artifact=input_artifact,
                output_artifact=cache_reuse["artifact"],
            )
            self.run_repository.save_validation_report(rights_report)
            methodology_report = build_methodology_report(
                run_id=run_id,
                cell=cell,
                capability=capability,
                parameters=parameters,
                input_artifact=input_artifact,
                output_artifact=cache_reuse["artifact"],
            )
            self.run_repository.save_validation_report(methodology_report)
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
                    "validation_report_ids": [
                        report["report_id"],
                        rights_report["report_id"],
                        methodology_report["report_id"],
                    ],
                    "resource_usage": {"duration_ms": 0},
                },
                event_type="run_succeeded_from_cache",
                event_detail={"source_run_id": cache_record["source_run_id"]},
            )
            return ExecutionResult(finished, cache_reuse["artifact"], report)

        failure_message = ""
        try:
            result = self.worker.execute(
                input_bytes=input_bytes,
                capability_version=capability["version"],
                input_crs=input_artifact["spatial"]["crs"],
                measurement_crs=cell["constraints"]["measurement_crs"],
                parameters=parameters,
                runtime_image_digest=image_digest,
            )
            if result.runtime_image_digest != image_digest:
                raise WorkerExecutionError(
                    "Worker result image digest differs from the pinned execution image."
                )
            inspection = inspect_vector_buffer_output(
                input_feature_collection=input_feature_collection,
                output_feature_collection=result.feature_collection,
                input_crs=input_artifact["spatial"]["crs"],
                expected_output_crs=output_contract.get("crs"),
                actual_output_crs=result.crs,
                permitted_geometry_types=permitted_geometry_types,
            )
            report = self._output_report(run_id, inspection)
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
                "crs": input_artifact["spatial"]["crs"],
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
                    "rights_provenance": {
                        "source_artifact": {
                            "artifact_id": input_artifact["artifact_id"],
                            "version": input_artifact["version"],
                        },
                        "declaration_status": (
                            "declared_unverified"
                            if input_artifact.get("rights") is not None
                            else "unknown"
                        ),
                    },
                },
            )
            rights_report = build_rights_provenance_report(
                run_id=run_id,
                input_artifact=input_artifact,
                output_artifact=output_artifact,
            )
            self.run_repository.save_validation_report(rights_report)
            methodology_report = build_methodology_report(
                run_id=run_id,
                cell=cell,
                capability=capability,
                parameters=parameters,
                input_artifact=input_artifact,
                output_artifact=output_artifact,
            )
            self.run_repository.save_validation_report(methodology_report)
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
                    "validation_report_ids": [
                        report["report_id"],
                        rights_report["report_id"],
                        methodology_report["report_id"],
                    ],
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

    @staticmethod
    def _cache_record(
        *,
        cell: dict[str, Any],
        capability: dict[str, Any],
        parameters: dict[str, Any],
        input_snapshot: dict[str, Any],
        implementation: dict[str, Any],
        manifest_checksum: str,
        runtime_image_digest: str,
    ) -> dict[str, str]:
        cache_policy = capability.get("cache_policy", "allowed")
        determinism = capability["determinism"]
        if cache_policy != "allowed":
            reason = (
                "conditional_cache_policy_not_implemented"
                if cache_policy == "conditional"
                else "capability_cache_disabled"
            )
            return {"status": "bypassed", "reason": reason}
        if determinism != "deterministic":
            return {"status": "bypassed", "reason": "capability_not_deterministic"}

        input_identity = {
            "input_port": input_snapshot["input_port"],
            "artifact": input_snapshot["artifact"],
            "checksum": input_snapshot["checksum"],
        }
        material = {
            "capability": {
                "capability_id": capability["capability_id"],
                "version": capability["version"],
            },
            "cell": {"cell_id": cell["cell_id"], "version": cell["version"]},
            "constraints": cell.get("constraints", {}),
            "implementation": {
                "implementation_id": implementation["implementation_id"],
                "version": implementation["version"],
                "manifest_checksum": manifest_checksum,
            },
            "input": input_identity,
            "normalized_parameters": parameters,
            "output_contracts": cell.get("output_contracts", {}),
            "runtime_image_digest": runtime_image_digest,
            "output_validator": {
                "name": _OUTPUT_VALIDATOR_NAME,
                "version": _OUTPUT_VALIDATOR_VERSION,
            },
        }
        canonical = json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "status": "miss",
            "cache_key": hashlib.sha256(canonical).hexdigest(),
        }

    def _find_cache_reuse(
        self,
        *,
        cache_record: dict[str, str],
        input_artifact: dict[str, Any],
        output_media_type: str,
        output_contract: dict[str, Any],
        permitted_geometry_types: set[str],
    ) -> dict[str, Any] | None:
        if cache_record["status"] != "miss":
            return None
        for candidate in self.run_repository.list_cache_candidates(
            cache_record["cache_key"]
        ):
            try:
                reuse = self._load_cache_candidate(
                    candidate=candidate,
                    input_artifact=input_artifact,
                    output_media_type=output_media_type,
                    output_contract=output_contract,
                    permitted_geometry_types=permitted_geometry_types,
                )
            except (
                ArtifactIntegrityError,
                ContractValidationError,
                FileNotFoundError,
                OSError,
                json.JSONDecodeError,
            ):
                continue
            if reuse is not None:
                return reuse
        return None

    def _load_cache_candidate(
        self,
        *,
        candidate: dict[str, Any],
        input_artifact: dict[str, Any],
        output_media_type: str,
        output_contract: dict[str, Any],
        permitted_geometry_types: set[str],
    ) -> dict[str, Any] | None:
        outputs = candidate.get("outputs", [])
        if len(outputs) != 1 or outputs[0].get("output_port") != "result":
            return None
        artifact_ref = outputs[0]["artifact"]
        artifact = self.artifact_store.get_artifact(
            artifact_ref["artifact_id"], artifact_ref["version"]
        )
        metadata = artifact.get("metadata", {})
        spatial = artifact.get("spatial", {})
        if not isinstance(metadata, dict) or not isinstance(spatial, dict):
            return None
        artifact_geometry_types = set(spatial.get("geometry_types", []))
        source_snapshots = candidate.get("input_snapshots", [])
        expected_input_ref = {
            "artifact_id": input_artifact["artifact_id"],
            "version": input_artifact["version"],
        }
        rights_provenance = metadata.get("rights_provenance")
        if (
            len(source_snapshots) != 1
            or source_snapshots[0].get("artifact") != expected_input_ref
            or not isinstance(rights_provenance, dict)
            or rights_provenance.get("source_artifact") != expected_input_ref
            or rights_provenance.get("declaration_status")
            != (
                "declared_unverified"
                if input_artifact.get("rights") is not None
                else "unknown"
            )
        ):
            return None
        if (
            self.worker.capability_id == "vector.reproject"
            and not coordinate_operation_evidence_valid(
                metadata.get("coordinate_operation")
            )
        ):
            return None
        if (
            artifact["media_type"] != output_media_type
            or spatial.get("crs") != output_contract.get("crs")
            or not artifact_geometry_types
            or not artifact_geometry_types.issubset(permitted_geometry_types)
            or artifact.get("rights") != input_artifact.get("rights")
            or metadata.get("output_port") != "result"
        ):
            return None

        producer_run_id = metadata.get("producer_run_id")
        if not isinstance(producer_run_id, str):
            return None
        producer_run = self.run_repository.get_run(producer_run_id)
        produced_by_source = any(
            output.get("artifact") == artifact_ref
            and output.get("output_port") == "result"
            for output in producer_run.get("outputs", [])
        )
        if producer_run["status"] != "succeeded" or not produced_by_source:
            return None

        source_report = None
        for report_id in candidate.get("validation_report_ids", []):
            report = self.run_repository.get_validation_report(report_id)
            if (
                report["subject"] == {"kind": "run", "id": candidate["run_id"]}
                and report["stage"] == "execution_output"
                and report["overall_status"] == "passed"
            ):
                source_report = report
                break
        if source_report is None:
            return None

        # A successful report from an older or incomplete validator is not
        # sufficient evidence for reuse under the current output contract.
        validator = source_report.get("validator")
        if not isinstance(validator, dict) or (
            validator.get("name") != _OUTPUT_VALIDATOR_NAME
            or validator.get("version") != _OUTPUT_VALIDATOR_VERSION
        ):
            return None
        findings = source_report.get("findings")
        if not isinstance(findings, list):
            return None
        finding_statuses: dict[str, str] = {}
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            code = finding.get("code")
            if isinstance(code, str) and code in (
                _REQUIRED_OUTPUT_FINDINGS | _REQUIRED_OUTPUT_CRS_FINDINGS
            ):
                if code in finding_statuses:
                    return None
                finding_statuses[code] = finding.get("status")
        if any(
            finding_statuses.get(code) != "passed"
            for code in _REQUIRED_OUTPUT_FINDINGS
        ):
            return None
        expected_crs_finding = self._expected_output_crs_finding()
        if (
            expected_crs_finding not in _REQUIRED_OUTPUT_CRS_FINDINGS
            or finding_statuses.get(expected_crs_finding) != "passed"
            or any(
                code in finding_statuses
                for code in _REQUIRED_OUTPUT_CRS_FINDINGS
                if code != expected_crs_finding
            )
        ):
            return None
        assessed = source_report.get("assessed_dimensions")
        if not isinstance(assessed, list) or any(
            not isinstance(dimension, str) for dimension in assessed
        ):
            return None
        assessed_dimensions = set(assessed)
        if not _REQUIRED_OUTPUT_DIMENSIONS.issubset(assessed_dimensions):
            return None

        self.artifact_store.read_bytes(artifact)
        return {
            "source_run": candidate,
            "source_report": source_report,
            "artifact": artifact,
        }

    @staticmethod
    def _expected_output_crs_finding() -> str:
        """Return the CRS invariant required for this capability's output."""
        return "output.crs_matches_input"

    @staticmethod
    def _cache_reuse_report(
        *,
        run_id: str,
        source_run: dict[str, Any],
        source_report: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_reference = (
            f"{artifact['artifact_id']}@{artifact['version']}"
        )
        return {
            "report_id": f"report:{run_id}:cache",
            "subject": {"kind": "run", "id": run_id},
            "stage": "execution_output",
            "overall_status": "passed",
            "created_at": utc_timestamp(),
            "validator": {"name": "foundry-cache-reuse", "version": "0.1.0"},
            "findings": [
                {
                    "code": "cache.source_output_reused",
                    "severity": "info",
                    "status": "passed",
                    "message": (
                        "Reused a checksum-verified immutable Artifact from "
                        "a previously successful and output-validated Run."
                    ),
                    "evidence": [
                        {
                            "kind": "run",
                            "reference": source_run["run_id"],
                            "summary": "Source Run with the same deterministic cache key.",
                        },
                        {
                            "kind": "validation_report",
                            "reference": source_report["report_id"],
                            "summary": "Source output validation passed.",
                        },
                        {
                            "kind": "artifact",
                            "reference": artifact_reference,
                            "summary": "Output Artifact checksum verified before reuse.",
                        },
                    ],
                }
            ],
            "summary": (
                "A prior validated output was reused after checking its source "
                "Run, validation evidence, Artifact metadata, and content checksum."
            ),
            "assessed_dimensions": [
                "source_run_status",
                "source_artifact_integrity",
                "source_output_validation_evidence",
            ],
            "unassessed_dimensions": [
                "fresh_geometry_revalidation",
                "methodological_suitability",
                "rights_security_policy",
            ],
        }

    def validate_worker_configuration(self) -> None:
        identifier_pattern = r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}"
        version_pattern = r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}"
        identifiers = (
            self.worker.worker_id,
            self.worker.implementation_id,
        )
        versions = (self.worker.implementation_version,)
        if any(
            not isinstance(value, str) or not re.fullmatch(identifier_pattern, value)
            for value in identifiers
        ):
            raise ExecutionPreconditionError(
                "Worker and implementation identities must be valid identifiers."
            )
        if any(
            not isinstance(value, str) or not re.fullmatch(version_pattern, value)
            for value in versions
        ):
            raise ExecutionPreconditionError(
                "Worker implementation version must be a valid version identifier."
            )
        if (
            not isinstance(self.worker.worker_type, str)
            or self.worker.worker_type not in {"local_docker", "remote"}
        ):
            raise ExecutionPreconditionError("Worker type is not supported by the Run contract.")

    @staticmethod
    def _required_port(ports: list[dict[str, Any]], port_id: str) -> dict[str, Any]:
        matches = [port for port in ports if port.get("port_id") == port_id]
        if len(matches) != 1:
            raise ExecutionPreconditionError(
                f"Capability must declare exactly one {port_id!r} port."
            )
        return matches[0]

    @staticmethod
    def _output_media_type(
        output_contract: dict[str, Any],
        capability_output_port: dict[str, Any],
    ) -> str:
        declared = output_contract.get("media_types", [])
        supported = capability_output_port.get("media_types", [])
        matches = [value for value in declared if value in supported]
        if len(matches) != 1:
            raise ExecutionPreconditionError(
                "Geo-Cell and capability output media types must agree on exactly one format."
            )
        return matches[0]

    @staticmethod
    def _normalize_parameters(
        cell: dict[str, Any],
        capability: dict[str, Any],
    ) -> dict[str, Any]:
        schema = capability["parameter_schema"]
        Draft202012Validator.check_schema(schema)
        parameters = dict(cell.get("parameters", {}))
        for name, definition in schema.get("properties", {}).items():
            if name not in parameters and "default" in definition:
                parameters[name] = definition["default"]
        errors = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(parameters),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ExecutionPreconditionError(
                f"Geo-Cell parameters do not satisfy the capability schema: {detail}"
            )
        return parameters

    @staticmethod
    def _validate_spatial_declarations(
        *,
        cell: dict[str, Any],
        capability: dict[str, Any],
        resolved_artifacts: dict[str, dict[str, Any]],
    ) -> None:
        validation_cell = deepcopy(cell)
        artifacts: dict[tuple[str, str], dict[str, Any]] = {}
        for port_id, binding in validation_cell.get("inputs", {}).items():
            artifact = resolved_artifacts.get(port_id)
            if artifact is None:
                raise ExecutionPreconditionError(
                    f"Spatial input Artifact for port {port_id!r} was not resolved."
                )
            artifact_ref = {
                "artifact_id": artifact["artifact_id"],
                "version": artifact["version"],
            }
            if binding.get("source") == "cell_output":
                validation_cell["inputs"][port_id] = {
                    "source": "artifact",
                    "artifact": artifact_ref,
                }
            elif binding.get("source") != "artifact" or binding.get(
                "artifact"
            ) != artifact_ref:
                raise ExecutionPreconditionError(
                    f"Resolved Artifact does not match input port {port_id!r}."
                )
            artifacts[(artifact["artifact_id"], artifact["version"])] = artifact

        key = (cell["cell_id"], cell["version"])
        capability_key = (capability["capability_id"], capability["version"])
        recipe_projection = {
            "nodes": [
                {
                    "node_id": cell["cell_id"],
                    "cell": {
                        "cell_id": cell["cell_id"],
                        "version": cell["version"],
                    },
                }
            ]
        }
        findings = validate_recipe_spatial(
            recipe_projection,
            cells={key: validation_cell},
            capabilities={capability_key: capability},
            artifacts=artifacts,
        )
        if findings:
            summary = "; ".join(f"{finding.code}: {finding.message}" for finding in findings)
            raise ExecutionPreconditionError(
                f"Spatial preconditions failed: {summary}"
            )

    @staticmethod
    def _output_report(run_id: str, inspection: Any) -> dict[str, Any]:
        findings = [
            {
                "code": finding.code,
                "severity": finding.severity,
                "status": finding.status,
                "message": finding.message,
                "json_pointer": finding.json_pointer,
            }
            for finding in inspection.findings
        ]
        passed = inspection.passed
        return {
            "report_id": f"report:{run_id}:output",
            "subject": {"kind": "run", "id": run_id},
            "stage": "execution_output",
            "overall_status": "passed" if passed else "failed",
            "created_at": utc_timestamp(),
            "validator": {
                "name": _OUTPUT_VALIDATOR_NAME,
                "version": _OUTPUT_VALIDATOR_VERSION,
            },
            "findings": findings,
            "summary": (
                "All output contract checks passed."
                if passed
                else "One or more output contract checks failed."
            ),
            "assessed_dimensions": [
                "feature_count",
                "feature_metadata",
                "crs",
                "geometry_type",
                "geometry_validity",
                "coordinate_finiteness",
                "dimensionality",
            ],
            "unassessed_dimensions": [
                "methodological_suitability",
                "rights_security_policy",
            ],
        }
