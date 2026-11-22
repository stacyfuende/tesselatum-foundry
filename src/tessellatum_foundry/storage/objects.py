"""Bounded-memory object storage for immutable geospatial source snapshots.

The S3-compatible adapter accepts an injected client (for example boto3's S3
client), keeping provider SDKs and credentials outside Foundry's core package.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class ObjectReceipt:
    """Verified identity and size metadata for one completed object upload."""

    object_uri: str
    checksum_sha256: str
    byte_size: int
    etag: str | None
    version_id: str | None
    parts: int


class ObjectStore(Protocol):
    """Minimal object-store contract required by source snapshot ingestion."""

    def upload_stream(
        self,
        stream: BinaryIO,
        *,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ObjectReceipt: ...


class S3ObjectStore:
    """S3-compatible streaming uploader with bounded memory and SHA-256.

    The client is injected so Foundry does not own credentials, region
    selection, endpoint configuration, retries, or SDK lifecycle. The caller
    must supply a unique key for each immutable snapshot attempt. Enforce
    no-overwrite/versioning policy at the bucket or gateway as well.
    """

    MIN_PART_SIZE = 5 * 1024 * 1024
    MAX_PART_SIZE = 5 * 1024 * 1024 * 1024
    MAX_PARTS = 10_000

    def __init__(self, client: Any, bucket: str, *, part_size: int = 16 * 1024 * 1024):
        if not bucket or not bucket.strip():
            raise ValueError("bucket must be a non-empty string.")
        if isinstance(part_size, bool) or not isinstance(part_size, int):
            raise TypeError("part_size must be an integer.")
        if part_size < self.MIN_PART_SIZE:
            raise ValueError(f"part_size must be at least {self.MIN_PART_SIZE} bytes.")
        if part_size > self.MAX_PART_SIZE:
            raise ValueError(f"part_size must not exceed {self.MAX_PART_SIZE} bytes.")
        self.client = client
        self.bucket = bucket
        self.part_size = part_size

    @staticmethod
    def _read_chunk(stream: BinaryIO, size: int) -> bytes:
        """Fill one bounded chunk unless EOF is reached."""
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise TypeError("upload stream must yield bytes.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def upload_stream(
        self,
        stream: BinaryIO,
        *,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ObjectReceipt:
        """Upload a binary stream without loading the full object into memory."""
        if not key or key.startswith("/") or any(part == ".." for part in key.split("/")):
            raise ValueError("key must be a safe, non-empty object key.")
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if metadata:
            if any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items()):
                raise TypeError("object metadata keys and values must be strings.")
            extra["Metadata"] = metadata

        digest = hashlib.sha256()
        byte_size = 0
        first = self._read_chunk(stream, self.part_size)

        if len(first) < self.part_size:
            digest.update(first)
            byte_size = len(first)
            response = self.client.put_object(
                Bucket=self.bucket, Key=key, Body=first, **extra
            )
            return ObjectReceipt(
                object_uri=f"s3://{self.bucket}/{key}",
                checksum_sha256=digest.hexdigest(),
                byte_size=byte_size,
                etag=response.get("ETag"),
                version_id=response.get("VersionId"),
                parts=1,
            )

        created = self.client.create_multipart_upload(
            Bucket=self.bucket, Key=key, **extra
        )
        upload_id = created["UploadId"]
        completed_parts: list[dict[str, Any]] = []
        part_number = 1
        chunk = first
        try:
            while chunk:
                if part_number > self.MAX_PARTS:
                    raise ValueError(
                        "S3 multipart upload exceeds 10,000 parts; increase part_size."
                    )
                digest.update(chunk)
                byte_size += len(chunk)
                response = self.client.upload_part(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                completed_parts.append(
                    {"PartNumber": part_number, "ETag": response["ETag"]}
                )
                part_number += 1
                chunk = self._read_chunk(stream, self.part_size)

            response = self.client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": completed_parts},
            )
        except Exception:
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id
            )
            raise

        return ObjectReceipt(
            object_uri=f"s3://{self.bucket}/{key}",
            checksum_sha256=digest.hexdigest(),
            byte_size=byte_size,
            etag=response.get("ETag"),
            version_id=response.get("VersionId"),
            parts=len(completed_parts),
        )
