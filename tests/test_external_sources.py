from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    GeoJsonFeatureCollectionReader,
    LocalFileSourceAdapter,
    SourceIntegrityError,
    SourceLimitExceeded,
    iter_external_feature_batches,
)
from tessellatum_foundry.sources.readers import FeatureReaderError
from tessellatum_foundry.validation.contracts import ContractRegistry


def reference(path: Path, **kwargs) -> ExternalDataReference:
    return ExternalDataReference(
        provider="local",
        dataset_id="fixture-roads",
        uri=path.resolve().as_uri(),
        **kwargs,
    )


def test_local_source_describes_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "roads.bin"
    source.write_bytes(b"0123456789")
    ref = reference(source, media_type="application/octet-stream")

    descriptor = LocalFileSourceAdapter().describe(ref)

    assert descriptor.byte_size == 10
    assert descriptor.media_type == "application/octet-stream"
    assert descriptor.reference == ref


def test_local_source_yields_bounded_chunks(tmp_path: Path) -> None:
    source = tmp_path / "roads.bin"
    source.write_bytes(b"0123456789")

    chunks = list(LocalFileSourceAdapter().iter_chunks(reference(source), chunk_size=4))

    assert chunks == [b"0123", b"4567", b"89"]
    assert max(map(len, chunks)) <= 4


def test_local_source_enforces_byte_budget(tmp_path: Path) -> None:
    source = tmp_path / "roads.bin"
    source.write_bytes(b"0123456789")

    chunks = LocalFileSourceAdapter().iter_chunks(
        reference(source), chunk_size=4, max_bytes=6
    )
    assert next(chunks) == b"0123"
    with pytest.raises(SourceLimitExceeded):
        next(chunks)


def test_local_source_verifies_declared_checksum_at_eof(tmp_path: Path) -> None:
    source = tmp_path / "roads.bin"
    source.write_bytes(b"roads")
    expected = hashlib.sha256(b"not roads").hexdigest()

    chunks = LocalFileSourceAdapter().iter_chunks(
        reference(source, checksum_sha256=expected), chunk_size=2
    )
    with pytest.raises(SourceIntegrityError):
        b"".join(chunks)


def test_reference_rejects_embedded_credentials_and_signed_query() -> None:
    with pytest.raises(ValueError, match="credentials"):
        ExternalDataReference(
            provider="example",
            dataset_id="roads",
            uri="https://user:secret@example.test/roads",
        )
    with pytest.raises(ValueError, match="query parameters"):
        ExternalDataReference(
            provider="example",
            dataset_id="roads",
            uri="https://example.test/roads?token=secret",
        )


def test_reference_rejects_invalid_checksum() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ExternalDataReference(
            provider="example",
            dataset_id="roads",
            uri="https://example.test/roads",
            checksum_sha256="not-a-digest",
        )


def test_external_reference_matches_canonical_schema(tmp_path: Path) -> None:
    source = tmp_path / "roads.parquet"
    source.write_bytes(b"fixture")
    reference_value = reference(source, media_type="application/vnd.apache.parquet")

    ContractRegistry().validate(
        "external-data-reference.schema.json", reference_value.to_dict()
    )


def test_geojson_feature_collection_reader_handles_arbitrary_chunk_boundaries() -> None:
    payload = (
        b'{"type":"FeatureCollection","features":['
        b'{"type":"Feature","properties":{"name":"caf\xc3\xa9"},"geometry":null},'
        b'{"type":"Feature","properties":{"n":2},"geometry":null}]}'
    )
    chunks = (payload[index : index + 3] for index in range(0, len(payload), 3))

    features = list(
        GeoJsonFeatureCollectionReader().iter_features(chunks, selection={})
    )

    assert [feature["properties"] for feature in features] == [
        {"name": "café"},
        {"n": 2},
    ]


def test_geojson_reader_accepts_features_before_type_and_empty_collection() -> None:
    payload = b'{"features":[],"bbox":[0,0,1,1],"type":"FeatureCollection"}'

    assert list(
        GeoJsonFeatureCollectionReader().iter_features([payload], selection={})
    ) == []


def test_geojson_reader_enforces_feature_size_limit() -> None:
    payload = (
        b'{"type":"FeatureCollection","features":['
        b'{"type":"Feature","properties":{"long":"0123456789"},"geometry":null}]}'
    )

    with pytest.raises(FeatureReaderError, match="byte limit"):
        list(
            GeoJsonFeatureCollectionReader(max_feature_bytes=32).iter_features(
                [payload], selection={}
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"type":"FeatureCollection","features":[{"type":"Point"}]}',
        b'{"type":"FeatureCollection","features":[{"type":"Feature"}',
        b'{"type":"FeatureCollection","features":[{"type":"Feature"},]}',
        b'{"type":"FeatureCollection","features":[],"features":[]}',
        b'{"type":"FeatureCollection","features":[]} trailing',
        b'{"type":"Feature","features":[]}',
    ],
)
def test_geojson_reader_rejects_malformed_or_non_collection_input(payload: bytes) -> None:
    with pytest.raises(FeatureReaderError):
        list(GeoJsonFeatureCollectionReader().iter_features([payload], selection={}))


def test_geojson_reader_rejects_selection() -> None:
    with pytest.raises(FeatureReaderError, match="does not support source selection"):
        list(
            GeoJsonFeatureCollectionReader().iter_features(
                [b'{"type":"FeatureCollection","features":[]}'],
                selection={"bbox": [0, 0, 1, 1]},
            )
        )


def test_external_geojson_source_flows_into_bounded_feature_batches(tmp_path: Path) -> None:
    source = tmp_path / "roads.geojson"
    source.write_bytes(
        b'{"type":"FeatureCollection","features":['
        b'{"type":"Feature","properties":{"id":1},"geometry":null},'
        b'{"type":"Feature","properties":{"id":2},"geometry":null}]}'
    )
    ref = reference(
        source,
        media_type="application/vnd.tessellatum.spatial-feature-collection+json",
    )

    batches = list(
        iter_external_feature_batches(
            ref,
            adapter=LocalFileSourceAdapter(),
            reader=GeoJsonFeatureCollectionReader(),
            chunk_size=7,
            max_batch_features=1,
            max_batch_bytes=1024,
        )
    )

    assert [batch.sequence for batch in batches] == [0, 1]
    assert [batch.first_feature_offset for batch in batches] == [0, 1]
    assert [batch.feature_count for batch in batches] == [1, 1]
