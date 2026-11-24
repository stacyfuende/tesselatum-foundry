from __future__ import annotations

import hashlib
from email.message import Message

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    HttpSourceAdapter,
    SourceAccessError,
    SourceIntegrityError,
    SourceLimitExceeded,
)


class FakeResponse:
    def __init__(self, payload: bytes = b"", headers: dict[str, str] | None = None):
        self.payload = payload
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.read_sizes: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk


def reference(**kwargs) -> ExternalDataReference:
    values = {
        "provider": "example",
        "dataset_id": "roads",
        "uri": "https://data.example.test/roads.geojson",
        "media_type": "application/geo+json",
    }
    values.update(kwargs)
    return ExternalDataReference(**values)


def test_https_adapter_describes_and_streams_with_runtime_headers():
    response = FakeResponse(
        b"abcdefgh",
        {"Content-Length": "8", "Content-Type": "application/geo+json", "ETag": '"v1"'},
    )
    requests = []

    def opener(request, *, timeout):
        requests.append((request, timeout))
        return response

    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        headers_resolver=lambda _ref: {"Authorization": "Bearer runtime-secret"},
        opener=opener,
    )
    ref = reference(etag='"v1"')

    descriptor = adapter.describe(ref)
    chunks = list(adapter.iter_chunks(ref, chunk_size=3))

    assert descriptor.byte_size == 8
    assert descriptor.media_type == "application/geo+json"
    assert chunks == [b"abc", b"def", b"gh"]
    assert all(item[0].get_header("Authorization") == "Bearer runtime-secret" for item in requests)
    assert "runtime-secret" not in str(ref.to_dict())
    assert max(response.read_sizes) <= 3


def test_https_adapter_rejects_non_allowlisted_and_non_https_uris():
    adapter = HttpSourceAdapter(allowed_hosts={"data.example.test"})
    assert adapter.supports(reference())
    assert not adapter.supports(reference(uri="https://evil.example.test/roads"))
    assert not adapter.supports(reference(uri="http://data.example.test/roads"))


def test_https_adapter_rejects_redirects_without_following_them():
    def opener(_request, *, timeout):
        raise RuntimeError("redirect to https://evil.example.test/?token=secret")

    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        headers_resolver=lambda _ref: {"Authorization": "Bearer secret"},
        opener=opener,
    )

    with pytest.raises(SourceAccessError, match="could not be retrieved") as error:
        list(adapter.iter_chunks(reference()))

    assert "secret" not in str(error.value)


def test_https_adapter_enforces_byte_budget():
    response = FakeResponse(b"abcdefgh")
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: response,
    )
    chunks = adapter.iter_chunks(reference(), chunk_size=3, max_bytes=4)
    assert next(chunks) == b"abc"
    with pytest.raises(SourceLimitExceeded):
        next(chunks)


def test_https_adapter_checks_etag_and_checksum_at_eof():
    payload = b"road-data"
    response = FakeResponse(payload, {"ETag": '"v2"'})
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: response,
    )
    with pytest.raises(SourceIntegrityError, match="ETag"):
        list(adapter.iter_chunks(reference(etag='"v1"')))

    response = FakeResponse(payload, {"ETag": '"v1"'})
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: response,
    )
    bad_checksum = hashlib.sha256(b"not-road-data").hexdigest()
    with pytest.raises(SourceIntegrityError, match="SHA-256"):
        list(adapter.iter_chunks(reference(checksum_sha256=bad_checksum)))


def test_https_adapter_redacts_runtime_credential_resolver_errors():
    def broken_resolver(_reference):
        raise RuntimeError("provider secret token")

    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        headers_resolver=broken_resolver,
        opener=lambda *_args, **_kwargs: pytest.fail("must not make request"),
    )
    with pytest.raises(SourceAccessError) as error:
        list(adapter.iter_chunks(reference()))
    assert "provider secret token" not in str(error.value)


def test_https_adapter_rejects_content_length_mismatch():
    response = FakeResponse(b"short", {"Content-Length": "20"})
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: response,
    )
    with pytest.raises(SourceIntegrityError, match="size changed"):
        list(adapter.iter_chunks(reference()))
