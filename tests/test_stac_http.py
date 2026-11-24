from __future__ import annotations

import urllib.error

import pytest

from tessellatum_foundry.sources.stac_http import (
    StacSearchTransportError,
    UrllibStacSearchTransport,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size):
        return self.payload[:size]


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, *, timeout):
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        return self.response


def transport(**kwargs):
    return UrllibStacSearchTransport(
        allowed_hosts={"catalog.example.test"}, **kwargs
    )


def test_transport_posts_bounded_request_and_injects_runtime_headers():
    value = transport(
        timeout=7,
        headers_resolver=lambda method, url: {"Authorization": "Bearer ephemeral"},
    )
    opener = FakeOpener(response=FakeResponse(b'{"features":[]}'))
    value._opener = opener
    payload = value.request(
        "POST",
        "https://catalog.example.test/search",
        body=b'{"limit":1}',
        max_bytes=1024,
    )
    assert payload == b'{"features":[]}'
    assert opener.request.get_method() == "POST"
    assert opener.request.data == b'{"limit":1}'
    assert opener.request.get_header("Authorization") == "Bearer ephemeral"
    assert opener.timeout == 7


def test_transport_rejects_unapproved_hosts_and_redirects():
    value = transport()
    with pytest.raises(StacSearchTransportError, match="allowlisted"):
        value.request(
            "GET", "https://evil.example.test/search", body=None, max_bytes=100
        )

    opener = FakeOpener(error=urllib.error.HTTPError(
        "https://catalog.example.test/search", 302, "redirect", {}, None
    ))
    value._opener = opener
    with pytest.raises(StacSearchTransportError, match="rejected"):
        value.request(
            "GET", "https://catalog.example.test/search", body=None, max_bytes=100
        )


def test_transport_enforces_response_limit_and_rejects_header_injection():
    value = transport()
    value._opener = FakeOpener(response=FakeResponse(b"12345"))
    with pytest.raises(StacSearchTransportError, match="byte limit"):
        value.request(
            "GET", "https://catalog.example.test/search", body=None, max_bytes=4
        )

    unsafe = transport(
        headers_resolver=lambda _method, _url: {"Host": "attacker.example"}
    )
    with pytest.raises(StacSearchTransportError, match="header policy"):
        unsafe.request(
            "GET", "https://catalog.example.test/search", body=None, max_bytes=100
        )


def test_transport_rejects_bad_method_body_and_timeout():
    with pytest.raises(ValueError, match="timeout"):
        transport(timeout=0)
    value = transport()
    with pytest.raises(StacSearchTransportError, match="method"):
        value.request(
            "PUT", "https://catalog.example.test/search", body=None, max_bytes=100
        )
    with pytest.raises(StacSearchTransportError, match="body"):
        value.request(
            "POST", "https://catalog.example.test/search", body=None, max_bytes=100
        )
