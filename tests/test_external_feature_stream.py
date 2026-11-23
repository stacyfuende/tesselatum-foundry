from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    ExternalFeatureStreamError,
    FeatureReaderError,
    LocalFileSourceAdapter,
    NdjsonFeatureReader,
    SourceIntegrityError,
    iter_external_feature_batches,
)


def feature(index: int) -> dict:
    return {
        "type": "Feature",
        "id": index,
        "geometry": {"type": "Point", "coordinates": [index, index]},
        "properties": {"index": index},
    }


def write_source(tmp_path: Path, payload: bytes, **reference_options):
    path = tmp_path / "features.ndjson"
    path.write_bytes(payload)
    reference = ExternalDataReference(
        provider="customer-filesystem",
        dataset_id="ndjson-fixture",
        uri=path.resolve().as_uri(),
        media_type="application/x-ndjson",
        **reference_options,
    )
    return path, reference


def test_ndjson_reader_handles_chunk_boundaries_and_final_record() -> None:
    payload = b"\r\n".join(
        json.dumps(feature(i), separators=(",", ":")).encode() for i in range(3)
    )
    reader = NdjsonFeatureReader()

    decoded = list(
        reader.iter_features(
            (payload[offset : offset + 11] for offset in range(0, len(payload), 11)),
            selection={},
        )
    )

    assert [item["id"] for item in decoded] == [0, 1, 2]


def test_external_stream_connects_local_source_reader_and_bounded_batches(tmp_path: Path) -> None:
    payload = b"\n".join(
        json.dumps(feature(i), separators=(",", ":")).encode() for i in range(5)
    )
    _, reference = write_source(tmp_path, payload)

    batches = list(
        iter_external_feature_batches(
            reference,
            adapter=LocalFileSourceAdapter(),
            reader=NdjsonFeatureReader(),
            chunk_size=13,
            max_batch_features=2,
            max_batch_bytes=512,
        )
    )

    assert [batch.feature_count for batch in batches] == [2, 2, 1]
    assert [batch.first_feature_offset for batch in batches] == [0, 2, 4]
    assert all(batch.byte_size <= 512 for batch in batches)
    decoded = [
        item["id"]
        for batch in batches
        for item in json.loads(batch.payload)["features"]
    ]
    assert decoded == list(range(5))


def test_external_stream_verifies_source_checksum_before_successful_exhaustion(
    tmp_path: Path,
) -> None:
    payload = json.dumps(feature(1)).encode()
    _, reference = write_source(
        tmp_path,
        payload,
        checksum_sha256=hashlib.sha256(b"different source").hexdigest(),
    )
    batches = iter_external_feature_batches(
        reference,
        adapter=LocalFileSourceAdapter(),
        reader=NdjsonFeatureReader(),
        chunk_size=5,
    )

    assert next(batches).feature_count == 1
    with pytest.raises(SourceIntegrityError):
        next(batches)


def test_ndjson_reader_rejects_unsupported_selection() -> None:
    reader = NdjsonFeatureReader()
    with pytest.raises(FeatureReaderError, match="does not support"):
        list(reader.iter_features([], selection={"bbox": [0, 0, 1, 1]}))


def test_ndjson_reader_rejects_oversized_record() -> None:
    reader = NdjsonFeatureReader(max_feature_bytes=32)
    with pytest.raises(FeatureReaderError, match="exceeds"):
        list(reader.iter_features([b'{"type":"Feature","properties":"' + b"x" * 40], selection={}))


def test_external_stream_rejects_unknown_media_type(tmp_path: Path) -> None:
    _, reference = write_source(
        tmp_path, b"", media_type="application/vnd.unknown-format"
    )
    with pytest.raises(ExternalFeatureStreamError, match="does not support"):
        list(
            iter_external_feature_batches(
                reference,
                adapter=LocalFileSourceAdapter(),
                reader=NdjsonFeatureReader(),
            )
        )
