from __future__ import annotations

import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.external_raster_runs import ExternalRasterWindowRunFactory
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import ExecutionPreconditionError


def make_cell():
    return {
        "cell_id": "elevation-window",
        "version": "1.0.0",
        "capability": {"capability_id": "raster.window", "version": "1.0.0"},
        "inputs": {
            "raster": {
                "source": "external",
                "reference": {
                    "provider": "example",
                    "dataset_id": "elevation-001",
                    "uri": "https://data.example.test/elevation.tif",
                    "etag": '"v1"',
                    "media_type": "image/geotiff",
                },
                "spatial": {
                    "kind": "raster",
                    "crs": {"authority": "EPSG", "code": 3857},
                    "raster": {
                        "width": 1024,
                        "height": 768,
                        "band_count": 1,
                        "dtypes": ["uint16"],
                        "resolution": [10, 10],
                    },
                },
            }
        },
        "parameters": {
            "row_offset": 10,
            "column_offset": 20,
            "height": 64,
            "width": 96,
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


def make_factory(tmp_path):
    return ExternalRasterWindowRunFactory(
        run_repository=RunRepository(tmp_path / "control"),
        capabilities=CapabilityRegistry(),
    )


def test_external_raster_factory_queues_run_without_ingesting_source(tmp_path):
    factory = make_factory(tmp_path)
    cell = make_cell()
    capability = factory.capabilities.get("raster.window", "1.0.0")

    run = factory.create_queued_run(cell=cell, capability=capability)

    assert run["status"] == "queued"
    assert run["capability"] == {"capability_id": "raster.window", "version": "1.0.0"}
    assert run["input_snapshots"] == []
    assert run["source_references"][0]["reference"]["uri"] == (
        "https://data.example.test/elevation.tif"
    )
    assert run["normalized_parameters"]["target_downsample"] == 1
    assert run["normalized_parameters"]["bands"] == [1]
    assert run["events"][0]["event_type"] == "run_queued"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda cell: cell["inputs"]["raster"]["reference"].pop("etag"), "strong ETag"),
        (lambda cell: cell["inputs"]["raster"]["spatial"].update(
            kind="vector", geometry_types=["Polygon"]
        ), "kind='raster'"),
        (lambda cell: cell["parameters"].update(width=2000), "extends beyond"),
        (lambda cell: cell["output_contracts"]["window"].update(
            crs={"authority": "EPSG", "code": 4326}
        ), "must match"),
    ],
)
def test_external_raster_factory_rejects_unsafe_or_inconsistent_declarations(
    tmp_path, mutate, message
):
    factory = make_factory(tmp_path)
    cell = make_cell()
    mutate(cell)
    with pytest.raises(ExecutionPreconditionError, match=message):
        factory.create_queued_run(
            cell=cell,
            capability=factory.capabilities.get("raster.window", "1.0.0"),
        )


def test_external_raster_factory_requires_exact_registered_capability(tmp_path):
    factory = make_factory(tmp_path)
    capability = factory.capabilities.get("raster.window", "1.0.0")
    capability["cache_policy"] = "allowed"
    with pytest.raises(ExecutionPreconditionError, match="differs"):
        factory.create_queued_run(cell=make_cell(), capability=capability)
