from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    HttpSourceAdapter,
    StacItemSourceResolver,
)


@pytest.mark.integration
def test_live_stac_item_resolves_public_provider_asset():
    """Opt-in smoke test against a real STAC Item endpoint.

    Set FOUNDRY_STAC_ITEM_URL, FOUNDRY_STAC_CATALOG_HOST,
    FOUNDRY_STAC_ASSET_HOSTS (comma-separated exact hosts), and
    FOUNDRY_STAC_ASSET_KEY. The item and asset must be public HTTPS URLs
    without signed query parameters.
    """
    item_url = os.getenv("FOUNDRY_STAC_ITEM_URL")
    catalog_host = os.getenv("FOUNDRY_STAC_CATALOG_HOST")
    asset_hosts = {
        host.strip()
        for host in os.getenv("FOUNDRY_STAC_ASSET_HOSTS", "").split(",")
        if host.strip()
    }
    asset_key = os.getenv("FOUNDRY_STAC_ASSET_KEY")
    if not all((item_url, catalog_host, asset_hosts, asset_key)):
        pytest.skip("Live STAC integration environment is not configured.")

    parsed = urlsplit(item_url)
    assert parsed.scheme == "https"
    assert parsed.hostname == catalog_host
    reference = ExternalDataReference(
        provider="stac-catalog",
        dataset_id="live-integration",
        uri=item_url,
        media_type="application/geo+json",
    )
    catalog_adapter = HttpSourceAdapter(allowed_hosts={catalog_host})
    resolver = StacItemSourceResolver(
        catalog_source=catalog_adapter,
        allowed_asset_hosts=asset_hosts,
    )

    asset = resolver.resolve(
        reference,
        catalog_id="live-integration",
        asset_key=asset_key,
    )
    assert asset.provider == "stac"
    assert asset.resource_id
    assert asset.uri.startswith("https://")
    assert urlsplit(asset.uri).hostname in asset_hosts
    assert asset.media_type
