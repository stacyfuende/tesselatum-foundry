"""Tests for bounded-memory S3-compatible source object uploads."""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest

from tessellatum_foundry.storage import S3ObjectStore


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: dict[str, list[bytes]] = {}
        self.aborted = False

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {"ETag": '"single"', "VersionId": "v1"}

    def create_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self.uploads["upload-1"] = []
        return {"UploadId": "upload-1"}

    def upload_part(self, **kwargs: Any) -> dict[str, str]:
        self.uploads[kwargs["UploadId"]].append(kwargs["Body"])
        return {"ETag": f'"part-{kwargs["PartNumber"]}"'}

    def complete_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        parts = self.uploads.pop(kwargs["UploadId"])
        self.objects[kwargs["Key"]] = b"".join(parts)
        return {"ETag": '"multipart"', "VersionId": "v2"}

    def abort_multipart_upload(self, **kwargs: Any) -> None:
        self.aborted = True
        self.uploads.pop(kwargs["UploadId"], None)


def test_small_upload_is_single_put_and_has_sha256() -> None:
    client = FakeS3Client()
    body = b"tiny source"
    store = S3ObjectStore(client, "foundry", part_size=5 * 1024 * 1024)

    receipt = store.upload_stream(io.BytesIO(body), key="landing/run-1/source.geojson")

    assert receipt.object_uri == "s3://foundry/landing/run-1/source.geojson"
    assert receipt.checksum_sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.byte_size == len(body)
    assert receipt.version_id == "v1"
    assert client.objects["landing/run-1/source.geojson"] == body


def test_large_upload_uses_bounded_multipart_chunks() -> None:
    client = FakeS3Client()
    part_size = 5 * 1024 * 1024
    body = b"a" * (part_size * 2 + 17)
    store = S3ObjectStore(client, "foundry", part_size=part_size)

    receipt = store.upload_stream(
        io.BytesIO(body), key="landing/run-2/source.parquet"
    )

    assert receipt.checksum_sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.byte_size == len(body)
    assert receipt.parts == 3
    assert client.objects["landing/run-2/source.parquet"] == body


@pytest.mark.parametrize("key", ["", "/absolute/key", "landing/../secret"])
def test_rejects_unsafe_object_keys(key: str) -> None:
    store = S3ObjectStore(FakeS3Client(), "foundry")
    with pytest.raises(ValueError, match="safe"):
        store.upload_stream(io.BytesIO(b"x"), key=key)


def test_rejects_part_size_below_s3_minimum() -> None:
    with pytest.raises(ValueError, match="at least"):
        S3ObjectStore(FakeS3Client(), "foundry", part_size=1024)
