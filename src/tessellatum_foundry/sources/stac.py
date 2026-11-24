"""STAC Item asset resolution into provider-neutral source references.

This module resolves catalog metadata only. It does not fetch catalog pages,
follow asset links, or transfer asset bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from .models import ExternalDataReference


MAX_STAC_ITEM_BYTES = 2 * 1024 * 1024


class StacResolutionError(ValueError):
    """A STAC Item or selected asset cannot become a safe source reference."""


def parse_stac_item(payload: bytes | str, *, max_bytes: int = MAX_STAC_ITEM_BYTES) -> dict[str, Any]:
    """Parse one bounded STAC Item JSON document."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer.")
    if isinstance(payload, bytes):
        if len(payload) > max_bytes:
            raise StacResolutionError("STAC Item exceeds the metadata byte limit.")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise StacResolutionError("STAC Item must be UTF-8 JSON.") from None
    elif isinstance(payload, str):
        if len(payload.encode("utf-8")) > max_bytes:
            raise StacResolutionError("STAC Item exceeds the metadata byte limit.")
        text = payload
    else:
        raise TypeError("payload must be bytes or str.")
    try:
        item = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        raise StacResolutionError("STAC Item is not valid JSON.") from None
    if not isinstance(item, dict):
        raise StacResolutionError("STAC Item root must be an object.")
    return item


def resolve_stac_asset(
    item: Mapping[str, Any],
    asset_key: str,
    *,
    catalog_id: str,
    allowed_hosts: set[str] | frozenset[str],
) -> ExternalDataReference:
    """Resolve one STAC Item asset to a safe, non-secret source reference.

    The caller supplies the catalog identity and the exact asset host policy.
    Signed query URLs are intentionally rejected; runtime credentials must be
    provided later through the source adapter's credential resolver.
    """
    if not isinstance(item, Mapping):
        raise TypeError("item must be a mapping.")
    if not isinstance(asset_key, str) or not asset_key.strip():
        raise StacResolutionError("asset_key must be non-empty.")
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        raise StacResolutionError("catalog_id must be non-empty.")
    if item.get("type") != "Feature" or not isinstance(item.get("stac_version"), str):
        raise StacResolutionError("A STAC Item Feature with stac_version is required.")
    item_id = item.get("id")
    collection_id = item.get("collection")
    assets = item.get("assets")
    if not isinstance(item_id, str) or not item_id.strip():
        raise StacResolutionError("STAC Item id is required.")
    if not isinstance(collection_id, str) or not collection_id.strip():
        raise StacResolutionError("STAC Item collection is required.")
    if not isinstance(assets, Mapping) or asset_key not in assets:
        raise StacResolutionError("Selected STAC asset does not exist.")
    asset = assets[asset_key]
    if not isinstance(asset, Mapping):
        raise StacResolutionError("Selected STAC asset must be an object.")
    href = asset.get("href")
    if not isinstance(href, str) or not href:
        raise StacResolutionError("Selected STAC asset href is required.")
    if not isinstance(allowed_hosts, (set, frozenset)) or not allowed_hosts:
        raise StacResolutionError("A non-empty exact asset-host allowlist is required.")
    hosts: set[str] = set()
    for value in allowed_hosts:
        if (
            not isinstance(value, str)
            or not value.strip()
            or "*" in value
            or "/" in value
            or ":" in value
            or "@" in value
        ):
            raise StacResolutionError("Asset hosts must be exact DNS hostnames.")
        normalized = value.strip().lower().rstrip(".")
        if not normalized or any(character.isspace() for character in normalized):
            raise StacResolutionError("Asset hosts must be exact DNS hostnames.")
        hosts.add(normalized)

    try:
        parsed = urlsplit(href)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise StacResolutionError(
            "STAC asset href is not an allowlisted HTTPS resource."
        ) from None
    if (
        parsed.scheme.lower() != "https"
        or not host
        or host not in hosts
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise StacResolutionError("STAC asset href is not an allowlisted HTTPS resource.")

    properties = item.get("properties")
    properties = properties if isinstance(properties, Mapping) else {}
    version = _first_string(properties, "version", "updated", "datetime", "created")
    media_type = asset.get("type")
    if media_type is not None and not isinstance(media_type, str):
        raise StacResolutionError("STAC asset type must be a media type string.")
    checksum = _sha256_from_multihash(asset.get("file:checksum"))
    selection = {"item_id": item_id, "asset_key": asset_key}
    return ExternalDataReference(
        provider="stac",
        dataset_id=f"{catalog_id}/{collection_id}",
        resource_id=f"{item_id}/{asset_key}",
        uri=href,
        version=version,
        checksum_sha256=checksum,
        media_type=media_type.split(";", 1)[0].strip().lower() if media_type else None,
        selection=selection,
    )


def _first_string(values: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _sha256_from_multihash(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StacResolutionError("STAC file:checksum must be a multihash string.")
    # Multihash sha2-256 is 0x12 followed by a 0x20 length and 32 digest bytes.
    normalized = value.lower()
    if normalized.startswith("1220") and len(normalized) == 68:
        try:
            bytes.fromhex(normalized)
        except ValueError:
            raise StacResolutionError("STAC file:checksum is malformed.") from None
        return normalized[4:]
    raise StacResolutionError("Only SHA-256 STAC file:checksum values are supported.")
