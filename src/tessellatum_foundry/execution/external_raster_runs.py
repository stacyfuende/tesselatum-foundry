"""Create immutable Run records for external raster.window computations."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from pyproj import CRS
from pyproj.exceptions import CRSError

from tessellatum_foundry.execution.capabilities import CapabilityRegistry, CapabilityRegistryError
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import ExecutionPreconditionError
from tessellatum_foundry.validation.contracts import ContractRegistry, ContractValidationError


class ExternalRasterWindowRunFactory:
    """Validate and queue raster.window Runs without reading or copying source data.

    A queued Run freezes the exact external locator, declared source grid,
    selected pixel window, bands and overview preference. Runtime authorization,
    ETag-pinned reads, execution and publication remain separate steps.
    """

    OUTPUT_MEDIA_TYPE = "application/vnd.tessellatum.raster-window"

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
        if isinstance(value, dict):
            authority, code = value.get("authority"), value.get("code")
            if (
                not isinstance(authority, str) or not authority.strip()
                or not isinstance(code, (str, int)) or isinstance(code, bool)
                or not str(code).strip()
            ):
                raise ValueError("CRS authority objects require a valid authority and code.")
            return CRS.from_authority(authority, str(code))
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return CRS.from_user_input(value)
        raise ValueError("CRS must be an authority object, authority string, or integer code.")

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
        except (CapabilityRegistryError, KeyError) as error:
            raise ExecutionPreconditionError(str(error)) from error
        if canonical.get("capability_id") != "raster.window":
            raise ExecutionPreconditionError(
                "ExternalRasterWindowRunFactory only supports raster.window."
            )
        if cell.get("capability") != {
            "capability_id": canonical["capability_id"],
            "version": canonical["version"],
        }:
            raise ExecutionPreconditionError(
                "Geo-Cell capability reference does not match the supplied contract."
            )

        input_ports = [p for p in canonical["input_ports"] if p.get("port_id") == "raster"]
        output_ports = [p for p in canonical["output_ports"] if p.get("port_id") == "window"]
        if len(input_ports) != 1 or len(output_ports) != 1:
            raise ExecutionPreconditionError("raster.window must declare raster and window ports.")

        binding = cell.get("inputs", {}).get("raster")
        if not isinstance(binding, dict) or binding.get("source") != "external":
            raise ExecutionPreconditionError("The raster input must use an external source binding.")
        reference = binding.get("reference")
        try:
            self.contracts.validate("external-data-reference.schema.json", reference)
        except ContractValidationError as error:
            raise ExecutionPreconditionError(f"External raster reference is invalid: {error}") from error

        parsed_uri = urlsplit(reference["uri"])
        if (
            parsed_uri.username is not None or parsed_uri.password is not None
            or parsed_uri.query or parsed_uri.fragment
        ):
            raise ExecutionPreconditionError(
                "External source URI must not embed credentials, query parameters, or fragments."
            )
        if reference.get("selection"):
            raise ExecutionPreconditionError("External raster source selection is not supported.")
        if reference.get("media_type") not in input_ports[0].get("accepted_media_types", []):
            raise ExecutionPreconditionError("External raster media type is not accepted.")
        etag = reference.get("etag")
        if not isinstance(etag, str) or not etag.strip() or etag.startswith("W/"):
            raise ExecutionPreconditionError(
                "raster.window requires a strong ETag for consistent range reads."
            )

        spatial = binding.get("spatial", {})
        if spatial.get("kind") != "raster":
            raise ExecutionPreconditionError("External raster binding must declare kind='raster'.")
        raster = spatial.get("raster", {})
        try:
            source_crs = self._resolve_crs(spatial["crs"])
        except (CRSError, KeyError, TypeError, ValueError) as error:
            raise ExecutionPreconditionError("External raster CRS must be resolvable.") from error
        if not source_crs:
            raise ExecutionPreconditionError("External raster CRS is required.")

        raw_parameters = deepcopy(cell.get("parameters", {}))
        parameter_schema = canonical["parameter_schema"]
        errors = sorted(Draft202012Validator(parameter_schema).iter_errors(raw_parameters),
                        key=lambda item: list(item.absolute_path))
        if errors:
            raise ExecutionPreconditionError(
                "Raster window parameters are invalid: " + "; ".join(e.message for e in errors)
            )
        parameters = {**raw_parameters}
        parameters.setdefault("target_downsample", 1)
        bands = tuple(parameters.get("bands", ()))
        if bands and any(band > raster["band_count"] for band in bands):
            raise ExecutionPreconditionError("Requested band is absent from the declared raster grid.")
        if (
            parameters["column_offset"] + parameters["width"] > raster["width"]
            or parameters["row_offset"] + parameters["height"] > raster["height"]
        ):
            raise ExecutionPreconditionError("Requested window extends beyond the declared raster grid.")

        output_contract = cell["output_contracts"].get("window")
        if not isinstance(output_contract, dict) or output_contract.get("data_kind") != "raster":
            raise ExecutionPreconditionError("Geo-Cell must declare a raster 'window' output contract.")
        if self.OUTPUT_MEDIA_TYPE not in output_contract.get("media_types", []):
            raise ExecutionPreconditionError("Output contract must accept the Foundry raster-window media type.")
        if output_contract.get("crs") is None:
            raise ExecutionPreconditionError("Raster window output contract must declare its CRS.")
        try:
            output_crs = self._resolve_crs(output_contract["crs"])
        except (CRSError, TypeError, ValueError) as error:
            raise ExecutionPreconditionError("Output raster CRS must be resolvable.") from error
        if not source_crs.equals(output_crs, ignore_axis_order=True):
            raise ExecutionPreconditionError("raster.window output CRS must match the source CRS.")

        source_references = [{"input_port": "raster", "reference": reference}]
        attempt = 1
        if retry_of_run_id is not None:
            previous = self.run_repository.get_run(retry_of_run_id)
            if previous.get("status") not in {"failed", "timed_out"}:
                raise ExecutionPreconditionError("Only failed or timed-out Runs can be retried.")
            if not previous.get("error", {}).get("retryable", False):
                raise ExecutionPreconditionError("The previous Run is not marked as retryable.")
            if previous.get("cell") != {"cell_id": cell["cell_id"], "version": cell["version"]}:
                raise ExecutionPreconditionError("A retry must use the same Geo-Cell version.")
            if previous.get("capability") != {
                "capability_id": canonical["capability_id"], "version": canonical["version"]
            }:
                raise ExecutionPreconditionError("A retry must use the same Capability version.")
            if previous.get("source_references", []) != source_references:
                raise ExecutionPreconditionError("A retry must preserve the exact external source reference.")
            if previous.get("normalized_parameters") != parameters:
                raise ExecutionPreconditionError("A retry must preserve normalized parameters.")
            if previous.get("input_snapshots") != []:
                raise ExecutionPreconditionError("A source-backed retry cannot introduce Artifact snapshots.")
            attempt = previous["attempt"] + 1

        return self.run_repository.create_queued_run(
            run_id=f"run:{uuid.uuid4().hex}",
            cell={"cell_id": cell["cell_id"], "version": cell["version"]},
            capability={"capability_id": canonical["capability_id"], "version": canonical["version"]},
            input_snapshots=[],
            normalized_parameters=parameters,
            source_references=source_references,
            attempt=attempt,
            retry_of_run_id=retry_of_run_id,
        )
