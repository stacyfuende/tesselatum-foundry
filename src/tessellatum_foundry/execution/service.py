"""Single-cell vector.buffer execution through a local Docker worker."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from tessellatum_foundry.execution.docker_worker import (
    DockerWorker,
    WorkerExecutionError,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.storage.artifacts import (
    FileSystemArtifactStore,
    utc_timestamp,
)
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.output import inspect_vector_buffer_output
from tessellatum_foundry.validation.spatial import validate_recipe_spatial


class ExecutionPreconditionError(ValueError):
    """Raised before a Run starts when its declarations are not executable."""


@dataclass(frozen=True)
class ExecutionResult:
    run: dict[str, Any]
    output_artifact: dict[str, Any] | None
    validation_report: dict[str, Any] | None


class VectorBufferRunService:
    """Execute one immutable Geo-Cell version and persist Run/output evidence."""

    IMPLEMENTATION_ID = "vector-buffer-shapely"
    IMPLEMENTATION_VERSION = "1.0.0"
    MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
        worker: DockerWorker,
        contracts: ContractRegistry | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_repository = run_repository
        self.worker = worker
        self.contracts = contracts or ContractRegistry()

    def execute(
        self,
        *,
        cell: dict[str, Any],
        capability: dict[str, Any],
        actor_id: str,
        retry_of_run_id: str | None = None,
    ) -> ExecutionResult:
        self.contracts.validate("cell.schema.json", cell)
        self.contracts.validate("capability.schema.json", capability)
        if capability.get("capability_id") != "vector.buffer":
            raise ExecutionPreconditionError("This execution service only supports vector.buffer.")
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
        if not isinstance(binding, dict) or binding.get("source") != "artifact":
            raise ExecutionPreconditionError(
                "The first local vector.buffer worker requires an immutable Artifact input."
            )
        artifact_ref = binding["artifact"]
        input_artifact = self.artifact_store.get_artifact(
            artifact_ref["artifact_id"], artifact_ref["version"]
        )
        accepted_media_types = input_port.get("accepted_media_types", [])
        if input_artifact["media_type"] not in accepted_media_types:
            raise ExecutionPreconditionError(
                "Input Artifact media type is not accepted by the capability contract."
            )
        if input_artifact.get("spatial", {}).get("kind") != "vector":
            raise ExecutionPreconditionError("Input Artifact must contain vector data.")
        if not input_artifact.get("spatial", {}).get("crs"):
            raise ExecutionPreconditionError("Input vector Artifact must declare its CRS.")
        input_bytes = self.artifact_store.read_bytes(input_artifact)
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
            input_artifact=input_artifact,
        )
        input_snapshot = {
            "input_port": "features",
            "artifact": artifact_ref,
            "checksum": input_artifact["checksum"]["value"],
        }
        attempt = 1
        if retry_of_run_id is not None:
            previous = self.run_repository.get_run(retry_of_run_id)
            if previous["status"] not in {"failed", "timed_out"}:
                raise ExecutionPreconditionError(
                    "Only failed or timed-out Runs can be retried."
                )
            if previous["cell"] != {
                "cell_id": cell["cell_id"],
                "version": cell["version"],
            }:
                raise ExecutionPreconditionError("A retry must use the same Geo-Cell version.")
            if previous.get("input_snapshots") != [input_snapshot]:
                raise ExecutionPreconditionError("A retry must use the same immutable inputs.")
            if previous.get("normalized_parameters") != parameters:
                raise ExecutionPreconditionError("A retry must use the same normalized parameters.")
            attempt = previous["attempt"] + 1

        run_id = f"run:{uuid.uuid4().hex}"
        run = self.run_repository.create_queued_run(
            run_id=run_id,
            cell={"cell_id": cell["cell_id"], "version": cell["version"]},
            input_snapshots=[input_snapshot],
            normalized_parameters=parameters,
            attempt=attempt,
            retry_of_run_id=retry_of_run_id,
        )

        try:
            image_digest = self.worker.image_digest()
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

        started_at = utc_timestamp()
        self.run_repository.transition(
            run_id,
            expected_status="queued",
            new_status="running",
            fields={
                "started_at": started_at,
                "worker": {
                    "worker_id": "local-docker-worker",
                    "worker_type": "local_docker",
                },
                "implementation": {
                    "implementation_id": self.IMPLEMENTATION_ID,
                    "version": self.IMPLEMENTATION_VERSION,
                },
                "runtime_image_digest": image_digest,
            },
            event_type="worker_started",
            event_detail={"runtime_image_digest": image_digest},
        )

        failure_message = ""
        try:
            result = self.worker.execute(
                input_bytes=input_bytes,
                input_crs=input_artifact["spatial"]["crs"],
                measurement_crs=cell["constraints"]["measurement_crs"],
                parameters=parameters,
                runtime_image_digest=image_digest,
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
                    "resource_usage": {
                        "duration_ms": result.duration_ms,
                        "scratch_bytes": len(output_bytes),
                    },
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
        input_artifact: dict[str, Any],
    ) -> None:
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
            cells={key: cell},
            capabilities={capability_key: capability},
            artifacts={
                (input_artifact["artifact_id"], input_artifact["version"]): input_artifact
            },
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
                "name": "foundry-vector-output-critic",
                "version": "0.1.0",
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
                "dimensionality",
            ],
            "unassessed_dimensions": [
                "methodological_suitability",
                "rights_security_policy",
            ],
        }
