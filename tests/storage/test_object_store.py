from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest

from tessellatum_foundry.storage.object_store import (
    InMemoryObjectStore,
    ObjectIntegrityError,
    ObjectNotFound,
    tenant_object_key,
    verify_object,
)


def test_put_get_and_immutable_object_key():
    store = InMemoryObjectStore()
    content = b"customer source bytes"
    receipt = store.put(
        object_key="tenants/abc/source/one",
        content=content,
        media_type="application/geo+json",
    )
    assert receipt.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert receipt.size_bytes == len(content)
    assert store.get(object_key=receipt.object_key) == content
    with pytest.raises(ObjectIntegrityError):
        store.put(
            object_key=receipt.object_key,
            content=b"different bytes",
            media_type="application/geo+json",
        )


def test_read_limit_and_missing_object():
    store = InMemoryObjectStore()
    store.put(object_key="tenant-a/source/one", content=b"1234", media_type="text/plain")
    with pytest.raises(ObjectIntegrityError):
        store.get(object_key="tenant-a/source/one", max_bytes=3)
    with pytest.raises(ObjectNotFound):
        store.get(object_key="tenant-a/source/missing")


def test_integrity_verification_checks_size_and_checksum():
    content = b"artifact"
    digest = hashlib.sha256(content).hexdigest()
    verify_object(
        content, expected_checksum_sha256=digest, expected_size_bytes=len(content)
    )
    with pytest.raises(ObjectIntegrityError):
        verify_object(
            content, expected_checksum_sha256=digest, expected_size_bytes=len(content) + 1
        )
    with pytest.raises(ObjectIntegrityError):
        verify_object(
            b"tampered", expected_checksum_sha256=digest, expected_size_bytes=len(content)
        )


def test_tenant_keys_are_non_identifying_and_reject_traversal():
    object_id = uuid4()
    first = tenant_object_key("tenant-secret-a", "source", object_id)
    second = tenant_object_key("tenant-secret-b", "source", object_id)
    assert first != second
    assert "tenant-secret-a" not in first
    assert ".." not in first
    with pytest.raises(ValueError):
        tenant_object_key("tenant-a", "../source", object_id)
