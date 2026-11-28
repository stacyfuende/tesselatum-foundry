from __future__ import annotations

import hashlib
import json

import pytest

from tessellatum_foundry.sources import (
    ExternalDataReference,
    StacResolutionError,
    parse_stac_item,
    resolve_stac_asset,
)


def item(**overrides):
    value = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "tile-17",
        "collection": "elevation",
        "properties": {"datetime": "2026-01-02T00:00:00Z"},
        "assets": {
            "data": {
                "href": "https://data.example.test/tile-17.tif",
                "type": "image/tiff; application=geotiff",
            }
        },
    }
    value.update(overrides)
    return value


def test_parse_stac_item_enforces_byte_limit_and_json_shape():
    parsed = parse_stac_item(json.dumps(item()).encode())
    assert parsed["id"] == "tile-17"
    with pytest.raises(StacResolutionError, match="byte limit"):
        parse_stac_item(b'{"type":"Feature"}', max_bytes=4)
    with pytest.raises(StacResolutionError, match="valid JSON"):
        parse_stac_item(b"{")
    with pytest.raises(StacResolutionError, match="root"):
        parse_stac_item(b"[]")


def test_resolves_stac_asset_to_non_secret_external_reference():
    digest = hashlib.sha256(b"raster").hexdigest()
    value = item()
    value["assets"]["data"]["file:checksum"] = "1220" + digest
    reference = resolve_stac_asset(
        value,
        "data",
        catalog_id="national-catalog",
        allowed_hosts={"data.example.test"},
    )
    assert isinstance(reference, ExternalDataReference)
    assert reference.provider == "stac"
    assert reference.dataset_id == "national-catalog/elevation"
    assert reference.resource_id == "tile-17/data"
    assert reference.version == "2026-01-02T00:00:00Z"
    assert reference.checksum_sha256 == digest
    assert reference.media_type == "image/tiff"
    assert reference.selection == {"item_id": "tile-17", "asset_key": "data"}


@pytest.mark.parametrize(
    "href",
    [
        "http://data.example.test/tile.tif",
        "https://evil.example.test/tile.tif",
        "https://user:pass@data.example.test/tile.tif",
        "https://data.example.test/tile.tif?token=secret",
        "https://data.example.test/tile.tif#fragment",
    ],
)
def test_rejects_unsafe_or_unapproved_asset_hrefs(href):
    value = item()
    value["assets"]["data"]["href"] = href
    with pytest.raises(StacResolutionError, match="allowlisted HTTPS"):
        resolve_stac_asset(
            value, "data", catalog_id="catalog", allowed_hosts={"data.example.test"}
        )


def test_rejects_missing_asset_and_unsupported_checksum():
    with pytest.raises(StacResolutionError, match="does not exist"):
        resolve_stac_asset(
            item(), "missing", catalog_id="catalog", allowed_hosts={"data.example.test"}
        )
    value = item()
    value["assets"]["data"]["file:checksum"] = "sha256:abc"
    with pytest.raises(StacResolutionError, match="Only SHA-256"):
        resolve_stac_asset(
            value, "data", catalog_id="catalog", allowed_hosts={"data.example.test"}
        )


def test_requires_stac_item_identity_and_collection():
    value = item()
    value.pop("collection")
    with pytest.raises(StacResolutionError, match="collection"):
        resolve_stac_asset(
            value, "data", catalog_id="catalog", allowed_hosts={"data.example.test"}
        )


@pytest.mark.parametrize(
    "href",
    [
        "https://data.example.test:bad/tile.tif",
        "https://data.example.test:444/tile.tif",
    ],
)
def test_rejects_invalid_or_non_default_asset_ports(href):
    value = item()
    value["assets"]["data"]["href"] = href
    with pytest.raises(StacResolutionError, match="allowlisted HTTPS"):
        resolve_stac_asset(
            value, "data", catalog_id="catalog", allowed_hosts={"data.example.test"}
        )


@pytest.mark.parametrize(
    "allowed_hosts",
    [set(), {"*.example.test"}, {"https://data.example.test"}, {""}],
)
def test_requires_nonempty_exact_dns_asset_host_allowlist(allowed_hosts):
    with pytest.raises(StacResolutionError, match="allowlist|exact DNS"):
        resolve_stac_asset(
            item(), "data", catalog_id="catalog", allowed_hosts=allowed_hosts
        )


def test_asset_host_matching_is_case_insensitive_and_ignores_terminal_dot():
    value = item()
    value["assets"]["data"]["href"] = "HTTPS://DATA.EXAMPLE.TEST./tile.tif"
    reference = resolve_stac_asset(
        value,
        "data",
        catalog_id="catalog",
        allowed_hosts={"Data.Example.Test."},
    )
    assert reference.uri == "HTTPS://DATA.EXAMPLE.TEST./tile.tif"
