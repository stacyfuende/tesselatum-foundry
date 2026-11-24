from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from tessellatum_foundry.sources import (
    StacApiSearchClient,
    UrllibStacSearchTransport,
    resolve_stac_asset,
)


@pytest.mark.integration
def test_live_stac_search_discovers_item_and_resolves_asset():
    """Opt-in Earth Search integration: spatial search through asset provenance."""
    search_url = os.getenv(
        "FOUNDRY_STAC_SEARCH_URL",
        "https://earth-search.aws.element84.com/v1/search",
    )
    asset_hosts = {
        host.strip()
        for host in os.getenv("FOUNDRY_STAC_ASSET_HOSTS", "").split(",")
        if host.strip()
    }
    if not asset_hosts:
        pytest.skip("Set FOUNDRY_STAC_ASSET_HOSTS to exact public asset hostnames.")

    parsed = urlsplit(search_url)
    assert parsed.scheme == "https"
    assert parsed.hostname
    transport = UrllibStacSearchTransport(
        allowed_hosts={parsed.hostname},
        timeout=30,
    )
    search = StacApiSearchClient(
        search_endpoint=search_url,
        allowed_hosts={parsed.hostname},
        transport=transport,
        max_page_bytes=8 * 1024 * 1024,
        max_pages=3,
        max_items=100,
    )
    items = list(
        search.search(
            bbox=[36.6, -1.5, 37.2, -1.0],
            datetime="2025-01-01T00:00:00Z/2025-02-01T00:00:00Z",
            collections=["sentinel-2-l2a"],
            limit=5,
        )
    )
    assert items, "Public catalog search returned no Items for the test area and interval."

    requested_asset_key = os.getenv("FOUNDRY_STAC_ASSET_KEY")
    resolved = None
    for item in items:
        assets = item.get("assets")
        if not isinstance(assets, dict):
            continue
        candidates = (
            [requested_asset_key]
            if requested_asset_key
            else list(assets)
        )
        for asset_key in candidates:
            asset = assets.get(asset_key)
            if not isinstance(asset, dict):
                continue
            href = asset.get("href")
            if not isinstance(href, str):
                continue
            asset_host = urlsplit(href).hostname
            if asset_host not in asset_hosts:
                continue
            try:
                resolved = resolve_stac_asset(
                    item,
                    asset_key,
                    catalog_id="earth-search-v1",
                    allowed_hosts=asset_hosts,
                )
            except ValueError:
                continue
            break
        if resolved is not None:
            break

    assert resolved is not None, (
        "No Item asset matched FOUNDRY_STAC_ASSET_HOSTS and the optional "
        "FOUNDRY_STAC_ASSET_KEY."
    )
    assert resolved.provider == "stac"
    assert resolved.uri.startswith("https://")
    assert urlsplit(resolved.uri).hostname in asset_hosts
    assert resolved.resource_id
