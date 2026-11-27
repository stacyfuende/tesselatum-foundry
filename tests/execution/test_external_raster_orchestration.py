from __future__ import annotations

import json
import struct

import pytest
from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.external_raster_orchestration import (
    ExternalRasterWindowRunOrchestrator,
)
from tessellatum_foundry.execution.external_raster_runs import ExternalRasterWindowRunFactory
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.sources.models import SourceDescriptor
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.raster_window import decode_raster_window_artifact


def tiled_geotiff():
    """Build a one-tile 32x16 EPSG:3857 classic TIFF with 8-bit samples."""
    tags = [
        (256, 4, 1, (32,)), (257, 4, 1, (16,)), (258, 3, 1, (8,)),
        (259, 3, 1, (1,)), (262, 3, 1, (1,)), (277, 3, 1, (1,)),
        (317, 3, 1, (1,)), (322, 4, 1, (32,)), (323, 4, 1, (16,)),
        (339, 3, 1, (1,)), (33550, 12, 3, (10.0, 10.0, 0.0)),
        (33922, 12, 6, (0.0, 0.0, 0.0, 500000.0, 1000000.0, 0.0)),
        (34735, 3, 8, (1, 1, 0, 1, 3072, 0, 1, 3857)),
        (324, 4, 1, (0,)), (325, 4, 1, (512,)),
    ]
    tags.sort()
    ifd_offset = 8
    extra_start = ifd_offset + 2 + len(tags) * 12 + 4
    extra = bytearray()
    entries = []
    for tag, typ, count, values in tags:
        fmt = {3: "H", 4: "I", 12: "d"}[typ]
        packed = struct.pack("<" + fmt * count, *values)
        if len(packed) <= 4:
            field = packed.ljust(4, b"\\x00")
        else:
            field = struct.pack("<I", extra_start + len(extra))
            extra.extend(packed)
        entries.append(struct.pack("<HHI", tag, typ, count) + field)
    pixel_offset = extra_start + len(extra)
    for index, (tag, _typ, _count, _values) in enumerate(tags):
        if tag == 324:
            entries[index] = struct.pack("<HHII", tag, 4, 1, pixel_offset)
    header = b"II" + struct.pack("<HI", 42, ifd_offset)
    directory = struct.pack("<H", len(entries)) + b"".join(entries) + struct.pack("<I", 0)
    pixels = bytes((index % 251 for index in range(512)))
    return header + directory + bytes(extra) + pixels


class MemoryRasterAdapter:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def supports(self, reference):
        return reference.uri == "https://example.test/dem.tif"

    def describe(self, reference):
        return SourceDescriptor(
            reference=reference,
            byte_size=len(self.payload),
            media_type="image/geotiff",
        )

    def read_range(self, reference, *, offset, length, max_range_bytes):
        self.calls.append((offset, length))
        return self.payload[offset:offset + length]


def make_cell():
    return {
        "cell_id": "dem-window",
        "version": "1.0.0",
        "capability": {"capability_id": "raster.window", "version": "1.0.0"},
        "inputs": {
            "raster": {
                "source": "external",
                "reference": {
                    "provider": "test-provider",
                    "dataset_id": "dem-001",
                    "uri": "https://example.test/dem.tif",
                    "etag": '"dem-v1"',
                    "media_type": "image/geotiff",
                },
                "spatial": {
                    "kind": "raster",
                    "crs": {"authority": "EPSG", "code": 3857},
                    "raster": {
                        "width": 32,
                        "height": 16,
                        "band_count": 1,
                        "dtypes": ["uint8"],
                        "resolution": [10, 10],
                    },
                },
            }
        },
        "parameters": {
            "row_offset": 2,
            "column_offset": 3,
            "height": 8,
            "width": 9,
            "bands": [1],
        },
        "output_contracts": {
            "window": {
                "data_kind": "raster",
                "media_types": ["application/vnd.tessellatum.raster-window"],
                "crs": {"authority": "EPSG", "code": 3857},
            }
        },
    }


def setup_run(tmp_path, *, adapter=None, authorizer=None, **limits):
    runs = RunRepository(tmp_path / "control")
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    capabilities = CapabilityRegistry()
    capability = capabilities.get("raster.window", "1.0.0")
    cell = make_cell()
    queued = ExternalRasterWindowRunFactory(
        run_repository=runs, capabilities=capabilities
    ).create_queued_run(cell=cell, capability=capability)
    adapter = adapter or MemoryRasterAdapter(tiled_geotiff())
    orchestrator = ExternalRasterWindowRunOrchestrator(
        artifact_store=store,
        run_repository=runs,
        source_adapter_resolver=lambda _reference: adapter,
        source_authorizer=authorizer or (lambda _reference, _actor: None),
        capabilities=capabilities,
        **limits,
    )
    return runs, store, cell, capability, queued, adapter, orchestrator


def test_external_raster_run_executes_validates_and_publishes_foundry_artifact(tmp_path):
    runs, store, cell, capability, queued, adapter, orchestrator = setup_run(tmp_path)

    result = orchestrator.execute(
        run_id=queued["run_id"],
        cell=cell,
        capability=capability,
        actor_id="user:test",
        artifact_id="dem.window",
        artifact_version="1.0.0",
    )

    assert result["run"]["status"] == "succeeded"
    assert result["run"]["worker"]["worker_type"] == "local_native"
    assert result["run"]["implementation"]["implementation_id"] == "raster-window-python"
    assert result["run"]["input_snapshots"] == []
    assert result["run"]["cache"]["status"] == "bypassed"
    assert result["source_range_requests"] == len(adapter.calls)
    assert result["source_range_requests"] > 0

    artifact = store.get_artifact("dem.window", "1.0.0")
    store.verify_artifact(artifact)
    decoded = decode_raster_window_artifact(store.read_bytes(artifact))
    assert decoded.header["window"] == {
        "row_offset": 2, "column_offset": 3, "height": 8, "width": 9
    }
    assert decoded.header["provenance"]["source_etag"] == '"dem-v1"'
    assert decoded.header["grid"]["crs"] == "EPSG:3857"
    assert decoded.header["grid"]["width"] == 9
    assert decoded.header["grid"]["height"] == 8
    assert decoded.header["grid"]["transform"] == [500030.0, 10.0, 0.0, 999980.0, 0.0, -10.0]
    assert len(decoded.validity) == 72
    report = runs.get_validation_report(
        artifact["metadata"]["validation_report_id"]
    )
    assert report["overall_status"] == "passed"
    assert report["stage"] == "execution_output"


def test_raster_run_source_authorization_failure_is_redacted_and_never_publishes(tmp_path):
    def deny(_reference, _actor):
        raise PermissionError("provider secret must not leak")

    runs, store, cell, capability, queued, _adapter, orchestrator = setup_run(
        tmp_path, authorizer=deny
    )
    with pytest.raises(PermissionError, match="authorization failed"):
        orchestrator.execute(
            run_id=queued["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="denied",
            artifact_version="1.0.0",
        )
    failed = runs.get_run(queued["run_id"])
    assert failed["status"] == "failed"
    assert "provider secret" not in json.dumps(failed)
    with pytest.raises(FileNotFoundError):
        store.get_artifact("denied", "1.0.0")


def test_raster_run_enforces_one_cumulative_source_range_budget(tmp_path):
    runs, store, cell, capability, queued, _adapter, orchestrator = setup_run(
        tmp_path, max_requests=1, max_source_bytes=1024, max_range_bytes=1024
    )
    with pytest.raises(Exception, match="budget|range"):
        orchestrator.execute(
            run_id=queued["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="budget-failure",
            artifact_version="1.0.0",
        )
    assert runs.get_run(queued["run_id"])["status"] == "failed"
    with pytest.raises(FileNotFoundError):
        store.get_artifact("budget-failure", "1.0.0")


def test_raster_run_can_reconcile_artifact_after_run_completion_interruption(tmp_path):
    runs, store, cell, capability, queued, _adapter, orchestrator = setup_run(tmp_path)
    original_reconcile = runs.reconcile_committed_output

    def interrupted(*_args, **_kwargs):
        raise OSError("simulated control-plane interruption")

    runs.reconcile_committed_output = interrupted
    with pytest.raises(OSError, match="simulated control-plane"):
        orchestrator.execute(
            run_id=queued["run_id"],
            cell=cell,
            capability=capability,
            actor_id="user:test",
            artifact_id="recoverable",
            artifact_version="1.0.0",
        )
    assert runs.get_run(queued["run_id"])["status"] == "running"
    runs.reconcile_committed_output = original_reconcile

    succeeded = orchestrator.reconcile_committed_output(
        run_id=queued["run_id"],
        artifact_id="recoverable",
        artifact_version="1.0.0",
    )
    assert succeeded["status"] == "succeeded"
