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
        self.status = 200

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


def range_response(payload, *, offset, total, etag='"v1"', status=206):
    response = FakeResponse(
        payload,
        {
            "Content-Range": f"bytes {offset}-{offset + len(payload) - 1}/{total}",
            "Content-Length": str(len(payload)),
            "ETag": etag,
            "Content-Encoding": "identity",
        },
    )
    response.status = status
    return response


def test_https_adapter_reads_exact_byte_range_with_validator():
    response = range_response(b"II*\x00", offset=0, total=4096)
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        return response

    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        headers_resolver=lambda _ref: {"Authorization": "Bearer runtime-secret"},
        opener=opener,
    )
    payload = adapter.read_range(
        reference(etag='"v1"'), offset=0, length=4
    )
    assert payload == b"II*\x00"
    assert requests[0].get_header("Range") == "bytes=0-3"
    assert requests[0].get_header("Accept-encoding") == "identity"
    assert requests[0].get_header("If-match") == '"v1"'
    assert requests[0].get_header("Authorization") == "Bearer runtime-secret"
    assert response.read_sizes == [5]


def test_https_adapter_rejects_range_fallback_and_wrong_content_range():
    full_response = FakeResponse(b"complete object")
    full_response.status = 200
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: full_response,
    )
    with pytest.raises(SourceIntegrityError, match="did not honor"):
        adapter.read_range(reference(), offset=0, length=4)

    wrong = range_response(b"abcd", offset=1, total=100)
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: wrong,
    )
    with pytest.raises(SourceIntegrityError, match="Content-Range"):
        adapter.read_range(reference(), offset=0, length=4)


def test_https_adapter_rejects_truncated_range_and_encoded_response():
    truncated = FakeResponse(
        b"abc",
        {
            "Content-Range": "bytes 0-3/100",
            "Content-Length": "4",
            "ETag": '"v1"',
            "Content-Encoding": "identity",
        },
    )
    truncated.status = 206
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: truncated,
    )
    with pytest.raises(SourceIntegrityError, match="incomplete"):
        adapter.read_range(reference(), offset=0, length=4)

    encoded = range_response(b"abcd", offset=0, total=100)
    encoded.headers["Content-Encoding"] = "gzip"
    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=lambda _request, **_kwargs: encoded,
    )
    with pytest.raises(SourceIntegrityError, match="content encoding"):
        adapter.read_range(reference(), offset=0, length=4)


def test_https_adapter_bounds_requested_range():
    adapter = HttpSourceAdapter(allowed_hosts={"data.example.test"})
    with pytest.raises(SourceLimitExceeded, match="range limit"):
        adapter.read_range(reference(), offset=0, length=5, max_range_bytes=4)
    with pytest.raises(ValueError, match="offset"):
        adapter.read_range(reference(), offset=-1, length=4)



def test_https_adapter_treats_if_match_precondition_failure_as_integrity_error():
    import urllib.error

    def opener(_request, **_kwargs):
        raise urllib.error.HTTPError(
            "https://data.example.test/roads.geojson",
            412,
            "precondition failed",
            {},
            None,
        )

    adapter = HttpSourceAdapter(
        allowed_hosts={"data.example.test"},
        opener=opener,
    )
    with pytest.raises(SourceIntegrityError, match="validator"):
        adapter.read_range(reference(etag='"v1"'), offset=0, length=4)
