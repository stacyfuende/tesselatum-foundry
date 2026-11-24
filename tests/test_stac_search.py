from __future__ import annotations

import json

import pytest

from tessellatum_foundry.sources import StacApiSearchClient, StacSearchError


class FakeSearchTransport:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def request(self, method, url, *, body, max_bytes):
        self.calls.append((method, url, body, max_bytes))
        if not self.pages:
            raise AssertionError("unexpected extra page request")
        return self.pages.pop(0)


def page(features, links=None):
    return json.dumps(
        {"type": "FeatureCollection", "features": features, "links": links or []}
    ).encode()


def item(item_id):
    return {"type": "Feature", "stac_version": "1.0.0", "id": item_id}


def client(transport, **limits):
    return StacApiSearchClient(
        search_endpoint="https://catalog.example.test/search",
        allowed_hosts={"catalog.example.test"},
        transport=transport,
        **limits,
    )


def test_search_posts_spatiotemporal_query_and_yields_paginated_items():
    transport = FakeSearchTransport(
        [
            page(
                [item("one")],
                [{"rel": "next", "href": "https://catalog.example.test/search?token=cursor", "method": "GET"}],
            ),
            page([item("two")]),
        ]
    )
    search = client(transport)
    found = list(
        search.search(
            bbox=[-10, -5, 10, 5],
            datetime="2026-01-01T00:00:00Z/2026-02-01T00:00:00Z",
            collections=["sentinel-2-l2a"],
            limit=25,
        )
    )
    assert [value["id"] for value in found] == ["one", "two"]
    method, url, body, max_bytes = transport.calls[0]
    assert method == "POST"
    assert url.endswith("/search")
    assert json.loads(body) == {
        "bbox": [-10, -5, 10, 5],
        "datetime": "2026-01-01T00:00:00Z/2026-02-01T00:00:00Z",
        "collections": ["sentinel-2-l2a"],
        "limit": 25,
    }
    assert transport.calls[1][0:2] == (
        "GET",
        "https://catalog.example.test/search?token=cursor",
    )
    assert max_bytes > 0


def test_search_supports_post_next_link_body():
    transport = FakeSearchTransport(
        [
            page(
                [item("one")],
                [{
                    "rel": "next",
                    "href": "https://catalog.example.test/search",
                    "method": "POST",
                    "body": {"token": "next-page"},
                }],
            ),
            page([item("two")]),
        ]
    )
    assert [value["id"] for value in client(transport).search()] == ["one", "two"]
    assert transport.calls[1][0] == "POST"
    assert json.loads(transport.calls[1][2]) == {"token": "next-page"}


def test_search_rejects_unapproved_next_host():
    transport = FakeSearchTransport(
        [page([item("one")], [{"rel": "next", "href": "https://evil.test/search"}])]
    )
    with pytest.raises(StacSearchError, match="allowlisted"):
        list(client(transport).search())


def test_search_rejects_cycles_and_page_limit():
    cyclic = FakeSearchTransport(
        [page([], [{"rel": "next", "href": "https://catalog.example.test/search"}])]
    )
    with pytest.raises(StacSearchError, match="cycle"):
        list(client(cyclic).search())

    pages = FakeSearchTransport(
        [
            page([], [{"rel": "next", "href": "https://catalog.example.test/page-2"}]),
            page([], [{"rel": "next", "href": "https://catalog.example.test/page-3"}]),
        ]
    )
    with pytest.raises(StacSearchError, match="page limit"):
        list(client(pages, max_pages=1).search())


def test_search_enforces_response_byte_and_item_limits():
    oversized = FakeSearchTransport([b"x" * 20])
    with pytest.raises(StacSearchError, match="byte limit"):
        list(client(oversized, max_page_bytes=10).search())

    too_many = FakeSearchTransport([page([item("one"), item("two")])])
    with pytest.raises(StacSearchError, match="Item limit"):
        list(client(too_many, max_items=1).search())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bbox": [0, 0, 1]},
        {"bbox": [0, 0, float("nan"), 1]},
        {"bbox": [2, 0, 1, 1]},
        {"bbox": [0, 0, 1, 1], "intersects": {"type": "Point", "coordinates": [0, 0]}},
        {"limit": 0},
        {"collections": [""]},
    ],
)
def test_search_validates_query_constraints(kwargs):
    with pytest.raises(StacSearchError):
        list(client(FakeSearchTransport([])).search(**kwargs))


def test_search_rejects_malformed_page_and_duplicate_next_links():
    malformed = FakeSearchTransport([b'{"type":"FeatureCollection","features":{}}'])
    with pytest.raises(StacSearchError, match="features"):
        list(client(malformed).search())

    duplicate = FakeSearchTransport(
        [
            page(
                [],
                [
                    {"rel": "next", "href": "https://catalog.example.test/one"},
                    {"rel": "next", "href": "https://catalog.example.test/two"},
                ],
            )
        ]
    )
    with pytest.raises(StacSearchError, match="at most one"):
        list(client(duplicate).search())
