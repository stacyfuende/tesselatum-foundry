"""Provider-neutral object storage contract and a test-only in-memory adapter.

Production providers must implement ObjectStore with private credentials,
tenant-scoped authorization, immutable writes, and durable cross-host reads.
The in-memory implementation exists only for deterministic unit tests.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

_KEY_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ObjectStoreError(RuntimeError):
    """Base error for object storage operations."""


class ObjectNotFound(ObjectStoreError):
    """The requested object does not exist."""


class ObjectIntegrityError(ObjectStoreError):
    """Stored bytes do not match their expected integrity metadata."""


@dataclass(frozen=True, slots=True)
class ObjectReceipt:
    """Opaque object reference and verified byte metadata."""

    object_key: str
    checksum_sha256: str
    size_bytes: int
    media_type: str


class ObjectStore(Protocol):
    """Minimal byte-store contract; metadata remains in the control plane."""

    def put(
        self, *, object_key: str, content: bytes, media_type: str
    ) -> ObjectReceipt:
        """Store bytes immutably and return their checksum and byte count."""

    def get(self, *, object_key: str, max_bytes: int | None = None) -> bytes:
        """Retrieve bytes, enforcing an optional hard size limit."""

    def delete(self, *, object_key: str) -> None:
        """Delete one object for a separately authorized retention process."""


def tenant_object_key(
    tenant_id: str, purpose: str, object_id: UUID | str
) -> str:
    """Build a non-identifying tenant namespace and reject unsafe key segments."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be a non-empty string.")
    if not isinstance(purpose, str) or not _KEY_PART.fullmatch(purpose):
        raise ValueError("purpose must be a safe object-key segment.")
    identity = str(object_id)
    if not _KEY_PART.fullmatch(identity):
        raise ValueError("object_id must be a safe object-key segment.")
    tenant_namespace = hashlib.sha256(tenant_id.strip().encode("utf-8")).hexdigest()
    return f"tenants/{tenant_namespace}/{purpose}/{identity}"


def verify_object(
    content: bytes, *, expected_checksum_sha256: str, expected_size_bytes: int
) -> None:
    """Verify retrieved or uploaded bytes against control-plane metadata."""
    if not isinstance(content, bytes):
        raise TypeError("Object content must be bytes.")
    if (
        not isinstance(expected_checksum_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_checksum_sha256)
    ):
        raise ValueError("expected_checksum_sha256 must be a lowercase SHA-256 digest.")
    if (
        isinstance(expected_size_bytes, bool)
        or not isinstance(expected_size_bytes, int)
        or expected_size_bytes < 0
    ):
        raise ValueError("expected_size_bytes must be a non-negative integer.")
    if len(content) != expected_size_bytes:
        raise ObjectIntegrityError("Stored object byte count does not match its metadata.")
    if hashlib.sha256(content).hexdigest() != expected_checksum_sha256:
        raise ObjectIntegrityError("Stored object checksum does not match its metadata.")


class InMemoryObjectStore:
    """Test-only immutable object store; never use for hosted or production jobs."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    def put(
        self, *, object_key: str, content: bytes, media_type: str
    ) -> ObjectReceipt:
        if not isinstance(object_key, str) or not object_key or object_key.startswith("/"):
            raise ValueError("object_key must be a non-empty relative key.")
        if any(part in {"", ".", ".."} for part in object_key.split("/")):
            raise ValueError("object_key contains an unsafe path segment.")
        if not isinstance(content, bytes):
            raise TypeError("Object content must be bytes.")
        if not isinstance(media_type, str) or not media_type.strip():
            raise ValueError("media_type must be a non-empty string.")
        checksum = hashlib.sha256(content).hexdigest()
        existing = self._objects.get(object_key)
        if existing is not None and existing != (content, media_type):
            raise ObjectIntegrityError("Object keys are immutable and already contain other data.")
        self._objects[object_key] = (content, media_type)
        return ObjectReceipt(object_key, checksum, len(content), media_type)

    def get(self, *, object_key: str, max_bytes: int | None = None) -> bytes:
        try:
            content, _ = self._objects[object_key]
        except KeyError as error:
            raise ObjectNotFound("Object was not found.") from error
        if max_bytes is not None:
            if (
                isinstance(max_bytes, bool)
                or not isinstance(max_bytes, int)
                or max_bytes < 0
            ):
                raise ValueError("max_bytes must be a non-negative integer or None.")
            if len(content) > max_bytes:
                raise ObjectIntegrityError("Object exceeds the configured read byte limit.")
        return content

    def delete(self, *, object_key: str) -> None:
        self._objects.pop(object_key, None)
