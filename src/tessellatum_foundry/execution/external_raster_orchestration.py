"""Execute an external raster.window Run through validation and publication."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from pyproj import CRS

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.external_raster_runs import ExternalRasterWindowRunFactory
from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.execution.service import ExecutionPreconditionError
from tessellatum_foundry.sources.models import ExternalDataReference
from tessellatum_foundry.sources.nodata import window_validity_mask
from tessellatum_foundry.sources.raster import BudgetedRasterRangeReader, RasterWindow
from tessellatum_foundry.sources.tiff import TiffRangeReader
from tessellatum_foundry.sources.window_read import read_tiff_window
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore, utc_timestamp
from tessellatum_foundry.storage.raster_window import encode_raster_window_artifact
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.raster_output import inspect_raster_window_output


class ExternalRasterWindowRunOrchestrator:
    """Authorize, read, validate and publish one source-backed raster.window Run.

    TIFF metadata and tile payloads are fetched through one cumulative,
    strong-ETag-pinned range budget. Source bytes remain external. The output
    Artifact is a Foundry Raster Window Container, never a TIFF/COG claim.
    """

    IMPLEMENTATION_ID = "raster-window-python"
    IMPLEMENTATION_VERSION = "1.0.0"
    WORKER_ID = "foundry-native-raster-window"

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
        source_adapter_resolver: Callable[[ExternalDataReference], Any],
        source_authorizer: Callable[[ExternalDataReference, str], None],
        contracts: ContractRegistry | None = None,
        capabilities: CapabilityRegistry | None = None,
        max_requests: int = 256,
        max_source_bytes: int = 64 * 1024 * 1024,
        max_range_bytes: int = 16 * 1024 * 1024,
        max_directories: int = 256,
        max_tiles: int = 256,
        max_output_bytes: int = 256 * 1024 * 1024,
        max_compressed_bytes: int = 16 * 1024 * 1024,
        max_decoded_bytes: int = 64 * 1024 * 1024,
        max_pixels_per_tile: int = 16 * 1024 * 1024,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_repository = run_repository
        self.source_adapter_resolver = source_adapter_resolver
        self.source_authorizer = source_authorizer
        self.contracts = contracts or ContractRegistry()
        self.capabilities = capabilities or CapabilityRegistry(contracts=self.contracts)
        self.max_requests = max_requests
        self.max_source_bytes = max_source_bytes
        self.max_range_bytes = max_range_bytes
        self.max_directories = max_directories
        self.max_tiles = max_tiles
        self.max_output_bytes = max_output_bytes
        self.max_compressed_bytes = max_compressed_bytes
        self.max_decoded_bytes = max_decoded_bytes
        self.max_pixels_per_tile = max_pixels_per_tile

    def execute(
        self,
        *,
        run_id: str,
        cell: dict[str, Any],
        capability: dict[str, Any],
        actor_id: str,
        artifact_id: str,
        artifact_version: str,
    ) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run.get("status") != "queued":
            raise RunStateError("Only a queued raster Run can be executed.")
        self.contracts.validate("cell.schema.json", cell)
        canonical = self.capabilities.require_exact(capability)
        if canonical.get("capability_id") != "raster.window":
            raise ExecutionPreconditionError("Only raster.window is supported.")
        if run.get("capability") != {
            "capability_id": canonical["capability_id"],
            "version": canonical["version"],
        } or run.get("cell") != {"cell_id": cell["cell_id"], "version": cell["version"]}:
            raise ExecutionPreconditionError(
                "Run identity differs from the supplied Cell or Capability."
            )
        binding = cell.get("inputs", {}).get("raster")
        if not isinstance(binding, dict) or binding.get("source") != "external":
            raise ExecutionPreconditionError("Run must use an external raster input.")
        reference_data = binding.get("reference")
        expected_sources = [{"input_port": "raster", "reference": reference_data}]
        if run.get("source_references") != expected_sources or run.get("input_snapshots") != []:
            raise ExecutionPreconditionError("Run source provenance differs from the Cell binding.")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ExecutionPreconditionError("A non-empty actor identity is required.")

        reference = ExternalDataReference(**reference_data)
        report_id: str | None = None
        try:
            self.source_authorizer(reference, actor_id)
            adapter = self.source_adapter_resolver(reference)
            if adapter is None or not adapter.supports(reference):
                raise ExecutionPreconditionError(
                    "No configured adapter supports this raster source."
                )
            descriptor = adapter.describe(reference)
            if descriptor.byte_size is None or descriptor.byte_size < 8:
                raise ExecutionPreconditionError(
                    "Raster source must expose a trustworthy byte size."
                )
            declared = binding["spatial"]["raster"]
            requested = run["normalized_parameters"]
            bounded = BudgetedRasterRangeReader(
                adapter,
                reference,
                max_requests=self.max_requests,
                max_total_bytes=self.max_source_bytes,
                max_range_bytes=self.max_range_bytes,
            )
            reader = TiffRangeReader(bounded)
            base = reader.read(file_size=descriptor.byte_size)
            if (
                base.metadata.width != declared["width"]
                or base.metadata.height != declared["height"]
                or base.metadata.band_count != declared["band_count"]
            ):
                raise ExecutionPreconditionError(
                    "Observed TIFF grid differs from the declared external raster grid."
                )
            if not base.metadata.crs:
                raise ExecutionPreconditionError("Observed TIFF has no supported embedded CRS.")
            crs_declaration = binding["spatial"]["crs"]
            if isinstance(crs_declaration, dict):
                declared_crs = CRS.from_authority(
                    crs_declaration["authority"], str(crs_declaration["code"])
                )
            else:
                declared_crs = CRS.from_user_input(crs_declaration)
            observed_crs = CRS.from_user_input(base.metadata.crs)
            if not declared_crs.equals(observed_crs, ignore_axis_order=True):
                raise ExecutionPreconditionError(
                    "Observed TIFF CRS differs from the declared external raster CRS."
                )

            started = self.run_repository.transition(
                run_id,
                expected_status="queued",
                new_status="running",
                fields={
                    "started_at": utc_timestamp(),
                    "worker": {"worker_id": self.WORKER_ID, "worker_type": "local_native"},
                    "implementation": {
                        "implementation_id": self.IMPLEMENTATION_ID,
                        "version": self.IMPLEMENTATION_VERSION,
                        "manifest_checksum": self._implementation_checksum(),
                    },
                    "cache": {
                        "status": "bypassed",
                        "reason": "external_source_integrity_not_cacheable",
                    },
                },
                event_type="external_raster_window_started",
                event_detail={
                    "source_provider": reference.provider,
                    "source_dataset_id": reference.dataset_id,
                },
            )
            execution_started = time.perf_counter()

            bands = tuple(requested.get("bands", ()))
            window = RasterWindow(
                row_offset=requested["row_offset"],
                column_offset=requested["column_offset"],
                height=requested["height"],
                width=requested["width"],
                bands=bands,
            )
            result = read_tiff_window(
                reader,
                file_size=descriptor.byte_size,
                window=window,
                target_downsample=requested.get("target_downsample", 1),
                max_directories=self.max_directories,
                max_tiles=self.max_tiles,
                max_output_bytes=self.max_output_bytes,
                max_compressed_bytes=self.max_compressed_bytes,
                max_decoded_bytes=self.max_decoded_bytes,
                max_pixels_per_tile=self.max_pixels_per_tile,
            )
            selected_metadata = result.overview.metadata
            selected_window = result.buffer.window
            validity = window_validity_mask(result.buffer, selected_metadata)
            inspection = inspect_raster_window_output(
                buffer=result.buffer,
                metadata=selected_metadata,
                requested_window=window,
                requested_bands=result.buffer.bands,
                validity=validity,
                max_output_bytes=self.max_output_bytes,
            )
            report_id = f"report:{uuid.uuid4().hex}"
            report = {
                "report_id": report_id,
                "subject": {"kind": "run", "id": run_id},
                "stage": "execution_output",
                "overall_status": "passed" if inspection.passed else "failed",
                "created_at": utc_timestamp(),
                "validator": {"name": "foundry-raster-window-critic", "version": "1.0.0"},
                "findings": [
                    {
                        "code": item.code,
                        "severity": item.severity,
                        "status": item.status,
                        "message": item.message,
                    }
                    for item in inspection.findings
                ],
                "summary": (
                    "Raster window output passed structural validation."
                    if inspection.passed
                    else "Raster window output failed structural validation."
                ),
                "assessed_dimensions": [
                    "pixel_window", "band_order", "sample_dtypes",
                    "byte_length", "validity_mask", "byte_order",
                ],
                "unassessed_dimensions": [
                    "source_licensing", "full_cog_conformance", "pixel_semantics",
                    "reprojection", "destination_grid_alignment",
                ],
            }
            self.run_repository.save_validation_report(report)
            if not inspection.passed:
                raise ExecutionPreconditionError("Raster output failed independent validation.")

            transform = list(selected_metadata.transform)
            transform[0] += (
                selected_window.column_offset * transform[1]
                + selected_window.row_offset * transform[2]
            )
            transform[3] += (
                selected_window.column_offset * transform[4]
                + selected_window.row_offset * transform[5]
            )
            grid = {
                "width": selected_window.width,
                "height": selected_window.height,
                "transform": transform,
                "crs": selected_metadata.crs,
                "band_count": len(result.buffer.bands),
            }
            provenance = {
                "source_provider": reference.provider,
                "source_dataset_id": reference.dataset_id,
                "source_uri": reference.uri,
                "source_etag": reference.etag,
                "source_checksum_sha256": reference.checksum_sha256,
                "source_byte_size": descriptor.byte_size,
                "source_range_requests": bounded.request_count,
                "source_bytes_requested": bounded.bytes_requested,
                "selected_ifd_offset": result.overview.directory.offset,
                "overview_factor": result.overview.factor,
                "requested_window": {
                    "row_offset": window.row_offset,
                    "column_offset": window.column_offset,
                    "height": window.height,
                    "width": window.width,
                },
                "selected_bands": list(result.buffer.bands),
            }
            payload = encode_raster_window_artifact(
                result.buffer,
                validity=validity,
                grid=grid,
                provenance=provenance,
            )
            pixel_width = (selected_metadata.transform[1] ** 2
                           + selected_metadata.transform[4] ** 2) ** 0.5
            pixel_height = (selected_metadata.transform[2] ** 2
                            + selected_metadata.transform[5] ** 2) ** 0.5
            artifact = self.artifact_store.put_bytes(
                artifact_id=artifact_id,
                version=artifact_version,
                content=payload,
                created_by=actor_id,
                media_type=ExternalRasterWindowRunFactory.OUTPUT_MEDIA_TYPE,
                format_name="tessellatum-raster-window/1.0.0",
                spatial={
                    "kind": "raster",
                    "crs": binding["spatial"]["crs"],
                    "raster": {
                        "width": result.buffer.window.width,
                        "height": result.buffer.window.height,
                        "band_count": len(result.buffer.bands),
                        "resolution": [pixel_width, pixel_height],
                    },
                },
                metadata={
                    "producer_run_id": run_id,
                    "producer_run_attempt": started["attempt"],
                    "producer_cell_id": cell["cell_id"],
                    "producer_cell_version": cell["version"],
                    "validation_report_id": report_id,
                    "raster_window": provenance,
                },
            )
            duration_ms = max(0, int((time.perf_counter() - execution_started) * 1000))
            succeeded = self.run_repository.reconcile_committed_output(
                run_id,
                artifact_store=self.artifact_store,
                artifact_id=artifact_id,
                artifact_version=artifact_version,
                output_port="window",
                validation_report_id=report_id,
                resource_usage={
                    "duration_ms": duration_ms,
                    "scratch_bytes": len(payload),
                },
            )
            return {
                "run": succeeded,
                "artifact": artifact,
                "validation_report": report,
                "window": result.buffer.window,
                "overview_factor": result.overview.factor,
                "ifd_offset": result.overview.directory.offset,
                "source_range_requests": bounded.request_count,
                "source_bytes_requested": bounded.bytes_requested,
            }
        except Exception as error:
            current = self.run_repository.get_run(run_id)
            if current.get("status") == "queued":
                self.run_repository.transition(
                    run_id,
                    expected_status="queued",
                    new_status="failed",
                    fields={
                        "finished_at": utc_timestamp(),
                        "error": {
                            "code": "external_raster_window.preflight_failed",
                            "message": f"Raster Run preflight failed ({type(error).__name__}).",
                            "retryable": isinstance(
                                error, (OSError, TimeoutError, ConnectionError)
                            ),
                        },
                    },
                    event_type="external_raster_window_preflight_failed",
                )
            elif current.get("status") == "running":
                # If publication committed before interruption, leave the Run
                # nonterminal so the explicit reconciler can finish it safely.
                try:
                    self.artifact_store.get_artifact(artifact_id, artifact_version)
                except FileNotFoundError:
                    self.run_repository.transition(
                        run_id,
                        expected_status="running",
                        new_status="failed",
                        fields={
                            "finished_at": utc_timestamp(),
                            "error": {
                                "code": "external_raster_window.execution_failed",
                                "message": f"Raster Run execution failed ({type(error).__name__}).",
                                "retryable": False,
                            },
                            **(
                                {"validation_report_ids": [report_id]}
                                if report_id is not None
                                else {}
                            ),
                        },
                        event_type="external_raster_window_failed",
                    )
            if isinstance(error, PermissionError):
                raise PermissionError("External raster source authorization failed.") from None
            raise

    def reconcile_committed_output(
        self, *, run_id: str, artifact_id: str, artifact_version: str
    ) -> dict[str, Any]:
        """Recover the Run lifecycle after Artifact metadata committed but Run did not."""
        artifact = self.artifact_store.get_artifact(artifact_id, artifact_version)
        report_id = artifact.get("metadata", {}).get("validation_report_id")
        if not isinstance(report_id, str) or not report_id:
            raise RunStateError("Committed raster Artifact has no validation report reference.")
        return self.run_repository.reconcile_committed_output(
            run_id,
            artifact_store=self.artifact_store,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            output_port="window",
            validation_report_id=report_id,
            resource_usage={
                "duration_ms": 0,
                "scratch_bytes": artifact["size_bytes"],
            },
        )

    def _implementation_checksum(self) -> str:
        from tessellatum_foundry.execution.implementations import ImplementationRegistry

        registry = ImplementationRegistry(contracts=self.contracts)
        return registry.manifest_checksum(self.IMPLEMENTATION_ID, self.IMPLEMENTATION_VERSION)
