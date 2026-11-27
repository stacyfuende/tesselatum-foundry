from __future__ import annotations

import pytest

from tessellatum_foundry.validation.contracts import ContractRegistry, ContractValidationError


def raster_cell():
    return {
        "cell_id": "elevation-window",
        "version": "1.0.0",
        "capability": {"capability_id": "raster.window", "version": "1.0.0"},
        "inputs": {
            "raster": {
                "source": "external",
                "reference": {
                    "provider": "example",
                    "dataset_id": "dem",
                    "uri": "https://data.example.test/dem.tif",
                    "media_type": "image/tiff",
                    "etag": '"v1"',
                },
                "spatial": {
                    "kind": "raster",
                    "crs": {"authority": "EPSG", "code": 3857},
                    "raster": {
                        "width": 4096,
                        "height": 4096,
                        "band_count": 1,
                        "dtypes": ["float32"],
                    },
                },
            }
        },
        "parameters": {
            "row_offset": 100,
            "column_offset": 200,
            "height": 256,
            "width": 256,
        },
        "output_contracts": {
            "window": {"data_kind": "raster"}
        },
    }


def test_cell_contract_accepts_explicit_external_raster_binding():
    ContractRegistry().validate("cell.schema.json", raster_cell())


def test_cell_contract_requires_raster_grid_metadata():
    cell = raster_cell()
    del cell["inputs"]["raster"]["spatial"]["raster"]
    with pytest.raises(ContractValidationError):
        ContractRegistry().validate("cell.schema.json", cell)
