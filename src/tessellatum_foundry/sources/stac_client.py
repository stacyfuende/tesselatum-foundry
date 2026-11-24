"""Bounded retrieval of STAC Item metadata through a configured source adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .models import ExternalDataReference
from .stac import parse_stac_item, resolve_stac_asset


class _ChunkSource(Protocol):
    def supports(self, reference: ExternalDataReference) -> bool: ...

    def iter_chunks(
        self,
        reference: ExternalDataReference,
        *,
        chunk_size: int = 8 * 1024 * 1024,
        max_bytes: int | None = None,
    ) -> Iterable[bytes]: ...


class StacItemSourceResolver:
    """Fetch one known STAC Item and resolve one asset without catalog crawling.

    The catalog Item endpoint and asset endpoint may have different host
    policies. Both are checked by their respective configured adapter/allowlist.
    """

    def __init__(
        self,
        *,
        catalog_source: _ChunkSource,
        allowed_asset_hosts: set[str] | frozenset[str],
        max_item_bytes: int = 2 * 1024 * 1024,
        chunk_size: int = 64 * 1024,
    ) -> None:
        if isinstance(max_item_bytes, bool) or not isinstance(max_item_bytes, int) or max_item_bytes < 1:
            raise ValueError("max_item_bytes must be a positive integer.")
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer.")
        self.catalog_source = catalog_source
        self.allowed_asset_hosts = frozenset(allowed_asset_hosts)
        self.max_item_bytes = max_item_bytes
        self.chunk_size = chunk_size

    def resolve(
        self,
        item_reference: ExternalDataReference,
        *,
        catalog_id: str,
        asset_key: str,
    ) -> ExternalDataReference:
        """Retrieve a known Item endpoint and return its selected asset reference."""
        if not self.catalog_source.supports(item_reference):
            raise ValueError("STAC Item endpoint is not supported by the catalog adapter.")
        chunks = self.catalog_source.iter_chunks(
            item_reference,
            chunk_size=self.chunk_size,
            max_bytes=self.max_item_bytes,
        )
        payload = bytearray()
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                raise TypeError("Catalog source adapters must yield bytes.")
            if len(payload) + len(chunk) > self.max_item_bytes:
                raise ValueError("STAC Item exceeds the metadata byte limit.")
            payload.extend(chunk)
        item = parse_stac_item(bytes(payload), max_bytes=self.max_item_bytes)
        return resolve_stac_asset(
            item,
            asset_key,
            catalog_id=catalog_id,
            allowed_hosts=self.allowed_asset_hosts,
        )
