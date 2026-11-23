"""Orchestrate a source-backed vector.buffer Run from authorization to publication."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tessellatum_foundry.execution.batches import VectorBufferBatchExecutor
from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.implementations import ImplementationRegistry
from tessellatum_foundry.execution.runs import RunRepository, RunStateError
from tessellatum_foundry.execution.streaming import StreamingRunFinalizer
from tessellatum_foundry.execution.streaming_pipeline import (
    StreamingExecutionResult,
    StreamingVectorBufferPipeline,
)
from tessellatum_foundry.execution.service import (
    ExecutionPreconditionError,
    VectorBufferRunService,
)
from tessellatum_foundry.sources.models import ExternalDataReference
from tessellatum_foundry.sources.readers import (
    GeoJsonFeatureCollectionReader,
    NdjsonFeatureReader,
)
from tessellatum_foundry.sources.stream import iter_external_feature_batches
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore, utc_timestamp
from tessellatum_foundry.storage.streaming import StreamingFeatureCollectionTransaction
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.streaming import VectorBufferStreamingValidator


class ExternalRunAuthorizationError(PermissionError):
    """Raised when the caller is not authorized to read a source."""


class ExternalVectorBufferRunOrchestrator:
    """Execute a queued external-source Run without taking custody of source data.

    Authorization and adapter resolution happen at execution time. Credentials
    are supplied only to the injected authorizer/adapter runtime and are never
    copied into Run records, transaction journals, validation reports, or errors.
    """

    def __init__(
        self,
        *,
        artifact_store: FileSystemArtifactStore,
        run_repository: RunRepository,
        worker: Any,
        source_adapter_resolver: Callable[[ExternalDataReference], Any],
        source_authorizer: Callable[[ExternalDataReference, str], None],
        transaction_root: Path,
        contracts: ContractRegistry | None = None,
        capabilities: CapabilityRegistry | None = None,
        implementations: ImplementationRegistry | None = None,
        chunk_size: int = 8 * 1024 * 1024,
        max_source_bytes: int | None = None,
        max_batch_features: int = 1_000,
        max_batch_bytes: int = 8 * 1024 * 1024,
        max_output_bytes: int = 2 * 1024 * 1024 * 1024,
        max_batches: int = 1_000_000,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_repository = run_repository
        self.worker = worker
        self.source_adapter_resolver = source_adapter_resolver
        self.source_authorizer = source_authorizer
        self.transaction_root = Path(transaction_root)
        self.contracts = contracts or ContractRegistry()
        self.capabilities = capabilities or CapabilityRegistry(contracts=self.contracts)
        self.implementations = implementations or ImplementationRegistry(
            contracts=self.contracts
        )
        self.chunk_size = chunk_size
        self.max_source_bytes = max_source_bytes
        self.max_batch_features = max_batch_features
        self.max_batch_bytes = max_batch_bytes
        self.max_output_bytes = max_output_bytes
        self.max_batches = max_batches

    def execute(
        self,
        *,
        run_id: str,
        cell: dict[str, Any],
        capability: dict[str, Any],
        actor_id: str,
        artifact_id: str,
        artifact_version: str,
    ) -> StreamingExecutionResult:
        """Claim and execute one queued source-backed Run attempt."""
        run = self.run_repository.get_run(run_id)
        if run.get("status") != "queued":
            raise RunStateError("Only a queued Run can be claimed for external execution.")
        self.contracts.validate("cell.schema.json", cell)
        canonical = self.capabilities.require_exact(capability)
        if canonical.get("capability_id") != "vector.buffer":
            raise ExecutionPreconditionError("Only vector.buffer is supported by this orchestrator.")
        if run.get("capability") != {
            "capability_id": canonical["capability_id"],
            "version": canonical["version"],
        } or run.get("cell") != {"cell_id": cell["cell_id"], "version": cell["version"]}:
            raise ExecutionPreconditionError("Run identity does not match the supplied Cell and Capability.")
        binding = cell.get("inputs", {}).get("features")
        if not isinstance(binding, dict) or binding.get("source") != "external":
            raise ExecutionPreconditionError(
                "Run must have an external features binding."
            )
        reference_data = binding.get("reference")
        expected_sources = [{"input_port": "features", "reference": reference_data}]
        if (
            run.get("source_references") != expected_sources
            or run.get("input_snapshots") != []
        ):
            raise ExecutionPreconditionError(
                "Run source provenance differs from the Cell binding."
            )
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ExecutionPreconditionError("A non-empty actor identity is required.")

        try:
            reference = ExternalDataReference(**reference_data)
            self.source_authorizer(reference, actor_id)
            adapter = self.source_adapter_resolver(reference)
            if adapter is None or not adapter.supports(reference):
                raise ExecutionPreconditionError(
                    "No configured source adapter supports this reference."
                )
            descriptor = adapter.describe(reference)
            self.worker_configuration_check()
            implementation = self.implementations.require_conformant(
                implementation_id=self.worker.implementation_id,
                version=self.worker.implementation_version,
                capability_id=canonical["capability_id"],
                capability_version=canonical["version"],
            )
            image_digest = self.worker.image_digest()
            if not isinstance(image_digest, str) or not re.fullmatch(
                r"sha256:[a-fA-F0-9]{64}", image_digest
            ):
                raise ExecutionPreconditionError("Worker did not provide an immutable image digest.")
            input_port = VectorBufferRunService._required_port(
                canonical["input_ports"], "features"
            )
            output_port = VectorBufferRunService._required_port(
                canonical["output_ports"], "result"
            )
            if reference.media_type not in input_port.get("accepted_media_types", []):
                raise ExecutionPreconditionError("Source media type is not accepted by the Capability.")
            spatial = binding["spatial"]
            input_crs = spatial["crs"]
            output_contract = cell.get("output_contracts", {}).get("result")
            if not isinstance(output_contract, dict):
                raise ExecutionPreconditionError("Cell must declare a result output contract.")
            output_media_type = VectorBufferRunService._output_media_type(
                output_contract, output_port
            )
            output_crs = output_contract.get("crs") or input_crs
            permitted = set(output_contract.get("geometry_types", [])).intersection(
                output_port.get("spatial", {}).get("geometry_types", [])
            )
            if not permitted:
                raise ExecutionPreconditionError(
                    "Cell and Capability have no compatible output geometry types."
                )
            if reference.media_type in GeoJsonFeatureCollectionReader.supported_media_types:
                reader = GeoJsonFeatureCollectionReader()
            elif reference.media_type in NdjsonFeatureReader.supported_media_types:
                reader = NdjsonFeatureReader()
            else:
                raise ExecutionPreconditionError(
                    "No incremental reader supports the source media type."
                )
            manifest_checksum = self.implementations.manifest_checksum(
                implementation["implementation_id"], implementation["version"]
            )
        except Exception as error:
            # Do not persist exception text: provider SDKs can include secrets in it.
            current = self.run_repository.get_run(run_id)
            if current.get("status") == "queued":
                self.run_repository.transition(
                    run_id,
                    expected_status="queued",
                    new_status="failed",
                    fields={
                        "finished_at": utc_timestamp(),
                        "error": {
                            "code": "external_run.preflight_failed",
                            "message": f"External Run preflight failed ({type(error).__name__}).",
                            "retryable": isinstance(
                                error, (OSError, TimeoutError, ConnectionError)
                            ),
                        },
                    },
                    event_type="external_run_preflight_failed",
                )
            raise

        started = self.run_repository.transition(
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
                    "implementation_id": implementation["implementation_id"],
                    "version": implementation["version"],
                    "manifest_checksum": manifest_checksum,
                },
                "runtime_image_digest": image_digest,
                "cache": {
                    "status": "bypassed",
                    "reason": "external_source_integrity_not_cacheable",
                },
            },
            event_type="external_source_worker_started",
            event_detail={"runtime_image_digest": image_digest},
        )

        transaction = StreamingFeatureCollectionTransaction(
            self.transaction_root,
            run_id=run_id,
            attempt=started["attempt"],
            max_output_bytes=self.max_output_bytes,
            max_batches=self.max_batches,
        )
        validator = VectorBufferStreamingValidator(
            input_crs=input_crs,
            expected_output_crs=output_crs,
            permitted_geometry_types=permitted,
        )
        pipeline = StreamingVectorBufferPipeline(
            executor=VectorBufferBatchExecutor(self.worker),
            validator=validator,
            finalizer=StreamingRunFinalizer(
                artifact_store=self.artifact_store,
                run_repository=self.run_repository,
            ),
            run_repository=self.run_repository,
        )
        batches = iter_external_feature_batches(
            reference,
            adapter=adapter,
            reader=reader,
            chunk_size=self.chunk_size,
            max_source_bytes=self.max_source_bytes,
            max_batch_features=self.max_batch_features,
            max_batch_bytes=self.max_batch_bytes,
        )
        completion = {
            "provider": reference.provider,
            "dataset_id": reference.dataset_id,
            **({"resource_id": reference.resource_id} if reference.resource_id else {}),
            **({"version": reference.version} if reference.version else {}),
            **({"etag": reference.etag} if reference.etag else {}),
            **({"checksum_sha256": reference.checksum_sha256} if reference.checksum_sha256 else {}),
            "media_type": reference.media_type,
            **({"byte_count": descriptor.byte_size} if descriptor.byte_size is not None else {}),
            **({"source_modified_at": descriptor.modified_at} if descriptor.modified_at else {}),
        }
        return pipeline.execute(
            batches,
            transaction=transaction,
            capability_version=canonical["version"],
            input_crs=input_crs,
            measurement_crs=cell["constraints"]["measurement_crs"],
            parameters=run["normalized_parameters"],
            runtime_image_digest=image_digest,
            source_completion=completion,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            output_port=output_port["port_id"],
            created_by=actor_id,
            output_crs=output_crs,
            media_type=output_media_type,
            metadata={
                "producer_cell_id": cell["cell_id"],
                "producer_cell_version": cell["version"],
                "source_provider": reference.provider,
                "source_dataset_id": reference.dataset_id,
            },
        )

    def worker_configuration_check(self) -> None:
        """Apply the same worker identity checks as the non-streaming service."""
        if (
            not isinstance(self.worker.worker_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}", self.worker.worker_id)
            or self.worker.worker_type not in {"local_docker", "remote"}
            or not isinstance(self.worker.implementation_id, str)
            or not isinstance(self.worker.implementation_version, str)
        ):
            raise ExecutionPreconditionError("Worker identity is not valid for the Run contract.")
