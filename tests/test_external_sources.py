from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    LocalFileSourceAdapter,
    SourceIntegrityError,
    SourceLimitExceeded,
)
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
