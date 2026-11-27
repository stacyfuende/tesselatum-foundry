from __future__ import annotations

import pytest

from tessellatum_foundry.sources.raster import RasterWindow
from tessellatum_foundry.sources.window_assembly import RasterWindowBuffer
from tessellatum_foundry.storage.raster_window import (
    RasterWindowArtifactError,
    decode_raster_window_artifact,
    encode_raster_window_artifact,
)


def make_buffer():
    return RasterWindowBuffer(
        window=RasterWindow(3, 5, 2, 2, (1,)),
        bands=(1,),
        dtypes=("uint16",),
        byte_order="little",
        samples=b"\x01\x00\x02\x00\x03\x00\x04\x00",
    )


def test_raster_window_artifact_round_trips_samples_validity_and_provenance():
    payload = encode_raster_window_artifact(
        make_buffer(),
        validity=(True, False, True, True),
        grid={
            "width": 100,
            "height": 80,
            "transform": [0, 10, 0, 800, 0, -10],
            "crs": "EPSG:3857",
        },
        provenance={"source_etag": '"v1"', "overview_factor": 2, "ifd_offset": 512},
    )

    decoded = decode_raster_window_artifact(payload)

    assert decoded.samples == make_buffer().samples
    assert decoded.validity == (True, False, True, True)
    assert decoded.header["window"] == {
        "row_offset": 3, "column_offset": 5, "height": 2, "width": 2
    }
    assert decoded.header["provenance"]["overview_factor"] == 2
    assert decoded.header["format_version"] == "1.0.0"


def test_raster_window_artifact_rejects_trailing_or_truncated_bytes():
    payload = encode_raster_window_artifact(
        make_buffer(), validity=(True,) * 4, grid={}, provenance={}
    )
    with pytest.raises(RasterWindowArtifactError, match="payload length"):
        decode_raster_window_artifact(payload + b"unexpected")
    with pytest.raises(RasterWindowArtifactError, match="truncated"):
        decode_raster_window_artifact(payload[:-1])


def test_raster_window_artifact_rejects_invalid_mask_and_non_json_metadata():
    with pytest.raises(RasterWindowArtifactError, match="one value per pixel"):
        encode_raster_window_artifact(
            make_buffer(), validity=(True,), grid={}, provenance={}
        )
    with pytest.raises(RasterWindowArtifactError, match="finite JSON"):
        encode_raster_window_artifact(
            make_buffer(), validity=(True,) * 4, grid={"resolution": float("nan")},
            provenance={}
        )
