from __future__ import annotations

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    StacItemSourceResolver,
)


class FakeCatalogSource:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.requested = None

    def supports(self, reference):
        return reference.uri.startswith("https://catalog.example.test/")

    def iter_chunks(self, reference, *, chunk_size, max_bytes):
        self.requested = (reference, chunk_size, max_bytes)
        for offset in range(0, len(self.payload), 7):
            yield self.payload[offset : offset + 7]


def catalog_reference():
    return ExternalDataReference(
        provider="catalog",
        dataset_id="national-catalog",
        uri="https://catalog.example.test/collections/elevation/items/tile-17",
        media_type="application/geo+json",
    )


def test_resolver_fetches_bounded_item_then_resolves_selected_asset():
    payload = (
        b'{"type":"Feature","stac_version":"1.0.0","id":"tile-17",'
        b'"collection":"elevation","properties":{"updated":"2026-03-01"},'
        b'"assets":{"data":{"href":"https://assets.example.test/tile.tif",'
        b'"type":"image/tiff"}}}'
    )
    source = FakeCatalogSource(payload)
    resolver = StacItemSourceResolver(
        catalog_source=source,
        allowed_asset_hosts={"assets.example.test"},
        max_item_bytes=2048,
        chunk_size=128,
    )
    result = resolver.resolve(
        catalog_reference(), catalog_id="national", asset_key="data"
    )
    assert result.uri == "https://assets.example.test/tile.tif"
    assert result.resource_id == "tile-17/data"
    assert source.requested == (catalog_reference(), 128, 2048)


def test_resolver_rejects_unapproved_catalog_endpoint_before_read():
    source = FakeCatalogSource(b"{}")
    resolver = StacItemSourceResolver(
        catalog_source=source, allowed_asset_hosts={"assets.example.test"}
    )
    unsafe = ExternalDataReference(
        provider="catalog",
        dataset_id="other",
        uri="https://unapproved.example.test/item",
    )
    with pytest.raises(ValueError, match="not supported"):
        resolver.resolve(unsafe, catalog_id="national", asset_key="data")
    assert source.requested is None


def test_resolver_rejects_metadata_over_limit():
    source = FakeCatalogSource(b"x" * 20)
    resolver = StacItemSourceResolver(
        catalog_source=source,
        allowed_asset_hosts={"assets.example.test"},
        max_item_bytes=10,
    )
    with pytest.raises(ValueError, match="byte limit"):
        resolver.resolve(
            catalog_reference(), catalog_id="national", asset_key="data"
        )
