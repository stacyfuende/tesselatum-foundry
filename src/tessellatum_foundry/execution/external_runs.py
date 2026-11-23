"""Create immutable Run records for Geo-Cells bound to external sources."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

from pyproj import CRS
from pyproj.exceptions import CRSError

from tessellatum_foundry.execution.capabilities import CapabilityRegistry, CapabilityRegistryError
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import ExecutionPreconditionError, VectorBufferRunService
from tessellatum_foundry.validation.contracts import ContractRegistry, ContractValidationError


class ExternalVectorBufferRunFactory:
    """Validate and queue source-backed vector.buffer Runs without ingesting data.

    This factory records the external source as immutable Run provenance and
    leaves source bytes in their original custody. It deliberately does not
    claim source authorization, read the resource, execute a worker, or publish
    an Artifact; those are separate runtime and policy gates.
    """

    def __init__(
        self,
        *,
        run_repository: RunRepository,
        contracts: ContractRegistry | None = None,
        capabilities: CapabilityRegistry | None = None,
    ) -> None:
        self.run_repository = run_repository
        self.contracts = contracts or ContractRegistry()
        self.capabilities = capabilities or CapabilityRegistry(contracts=self.contracts)

    @staticmethod
    def _resolve_crs(value: Any) -> CRS:
        """Resolve a declared CRS using pyproj without guessing missing values."""
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError("CRS must be an authority string or integer EPSG code.")
        return CRS.from_user_input(value)

    def create_queued_run(
        self,
        *,
        cell: dict[str, Any],
        capability: dict[str, Any],
        retry_of_run_id: str | None = None,
    ) -> dict[str, Any]:
        cell = deepcopy(cell)
        capability = deepcopy(capability)
        self.contracts.validate("cell.schema.json", cell)
        self.contracts.validate("capability.schema.json", capability)
        try:
            canonical = self.capabilities.require_exact(capability)
        except CapabilityRegistryError as error:
            raise ExecutionPreconditionError(str(error)) from error
        if canonical.get("capability_id") != "vector.buffer":
            raise ExecutionPreconditionError(
                "ExternalVectorBufferRunFactory only supports vector.buffer."
            )
        if cell.get("capability") != {
            "capability_id": canonical["capability_id"],
            "version": canonical["version"],
        }:
            raise ExecutionPreconditionError(
                "Geo-Cell capability reference does not match the supplied contract."
            )

        input_ports = [
            port for port in canonical["input_ports"]
            if port.get("port_id") == "features"
        ]
        if len(input_ports) != 1:
            raise ExecutionPreconditionError(
                "Capability must declare exactly one features input port."
            )
        binding = cell.get("inputs", {}).get("features")
        if not isinstance(binding, dict) or binding.get("source") != "external":
            raise ExecutionPreconditionError(
                "The features input must use an external source binding."
            )
        reference = binding["reference"]
        try:
            self.contracts.validate("external-data-reference.schema.json", reference)
        except ContractValidationError as error:
            raise ExecutionPreconditionError(
                f"External source reference is invalid: {error}"
            ) from error

        parsed_uri = urlsplit(reference["uri"])
        if (
            parsed_uri.username is not None
            or parsed_uri.password is not None
            or parsed_uri.query
            or parsed_uri.fragment
        ):
            raise ExecutionPreconditionError(
                "External source URI must not embed credentials, query parameters, or fragments."
            )
        if reference.get("selection"):
            raise ExecutionPreconditionError(
                "This initial external Run path does not support source selection "
                "or query pushdown."
            )
        media_type = reference.get("media_type")
        if not media_type or media_type not in input_ports[0].get("accepted_media_types", []):
            raise ExecutionPreconditionError(
                "External source media_type must be declared and accepted by "
                "the features input port."
            )

        spatial = binding["spatial"]
        if spatial.get("kind") != "vector" or not spatial.get("geometry_types"):
            raise ExecutionPreconditionError(
                "External features binding must declare vector geometry types and CRS."
            )
        declared_types = set(spatial["geometry_types"])
        accepted_types = set(input_ports[0].get("spatial", {}).get("geometry_types", []))
        if accepted_types and not declared_types.issubset(accepted_types):
            raise ExecutionPreconditionError(
                "External source geometry types exceed the Capability input contract."
            )
        parameters = VectorBufferRunService._normalize_parameters(cell, canonical)
        try:
            source_crs = self._resolve_crs(spatial["crs"])
            measurement_crs = self._resolve_crs(cell["constraints"]["measurement_crs"])
        except (CRSError, KeyError, TypeError, ValueError) as error:
            raise ExecutionPreconditionError(
                "External source and measurement CRS declarations must be resolvable."
            ) from error
        if not measurement_crs.is_projected or not source_crs.equals(
            measurement_crs, ignore_axis_order=True
        ):
            raise ExecutionPreconditionError(
                "vector.buffer requires the external source CRS to match "
                "its projected measurement CRS."
            )
        if parameters.get("single_sided", False) and declared_types != {"LineString"}:
            raise ExecutionPreconditionError(
                "Single-sided vector.buffer requires only LineString source geometry."
            )
        source_references = [{
            "input_port": "features",
            "reference": reference,
        }]

        attempt = 1
        if retry_of_run_id is not None:
            previous = self.run_repository.get_run(retry_of_run_id)
            if previous.get("status") not in {"failed", "timed_out"}:
                raise ExecutionPreconditionError(
                    "Only failed or timed-out Runs can be retried."
                )
            if not previous.get("error", {}).get("retryable", False):
                raise ExecutionPreconditionError(
                    "The previous Run is not marked as retryable."
                )
            if previous.get("cell") != {
                "cell_id": cell["cell_id"],
                "version": cell["version"],
            }:
                raise ExecutionPreconditionError(
                    "A retry must use the same Geo-Cell version."
                )
            if previous.get("capability") != {
                "capability_id": canonical["capability_id"],
                "version": canonical["version"],
            }:
                raise ExecutionPreconditionError(
                    "A retry must use the same Capability version."
                )
            if previous.get("source_references", []) != source_references:
                raise ExecutionPreconditionError(
                    "A retry must preserve the exact external source reference."
                )
            if previous.get("normalized_parameters") != parameters:
                raise ExecutionPreconditionError(
                    "A retry must preserve normalized parameters."
                )
            if previous.get("input_snapshots") != []:
                raise ExecutionPreconditionError(
                    "A source-backed retry cannot introduce Artifact input snapshots."
                )
            attempt = previous["attempt"] + 1

        run_id = f"run:{uuid.uuid4().hex}"
        return self.run_repository.create_queued_run(
            run_id=run_id,
            cell={"cell_id": cell["cell_id"], "version": cell["version"]},
            capability={
                "capability_id": canonical["capability_id"],
                "version": canonical["version"],
            },
            input_snapshots=[],
            normalized_parameters=parameters,
            source_references=source_references,
            attempt=attempt,
            retry_of_run_id=retry_of_run_id,
        )
