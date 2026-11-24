"""Bounded STAC API Item search with explicit pagination and host policy.

The transport is injected so provider credentials and HTTP policy stay outside
catalog definitions. It must enforce timeouts, byte limits, TLS validation and
must not follow redirects to unapproved hosts.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit


class StacSearchError(ValueError):
    """A STAC search request or response violates the bounded search contract."""


class StacSearchTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        max_bytes: int,
    ) -> bytes: ...


class StacApiSearchClient:
    """Search one STAC API endpoint and follow only allowlisted pagination links.

    Search responses are streamed page-by-page to the caller. Each page is
    fully bounded and parsed before its Items are yielded; the complete result
    set is never accumulated in memory.
    """

    def __init__(
        self,
        *,
        search_endpoint: str,
        allowed_hosts: set[str] | frozenset[str],
        transport: StacSearchTransport,
        max_page_bytes: int = 8 * 1024 * 1024,
        max_pages: int = 100,
        max_items: int = 100_000,
    ) -> None:
        if (
            isinstance(max_page_bytes, bool)
            or not isinstance(max_page_bytes, int)
            or max_page_bytes < 1
        ):
            raise ValueError("max_page_bytes must be a positive integer.")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer.")
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
            raise ValueError("max_items must be a positive integer.")
        self.allowed_hosts = self._normalize_hosts(allowed_hosts)
        self.search_endpoint = self._validate_url(search_endpoint)
        self.transport = transport
        self.max_page_bytes = max_page_bytes
        self.max_pages = max_pages
        self.max_items = max_items

    def search(
        self,
        *,
        bbox: list[float] | tuple[float, ...] | None = None,
        intersects: Mapping[str, Any] | None = None,
        datetime: str | None = None,
        collections: list[str] | tuple[str, ...] | None = None,
        ids: list[str] | tuple[str, ...] | None = None,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Yield STAC Items for a validated spatial/temporal query."""
        query = self._build_query(
            bbox=bbox,
            intersects=intersects,
            datetime=datetime,
            collections=collections,
            ids=ids,
            limit=limit,
        )
        method = "POST"
        url = self.search_endpoint
        try:
            body: bytes | None = json.dumps(
                query, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise StacSearchError("STAC search constraints must be JSON-compatible.") from None
        visited: set[str] = set()
        page_count = 0
        item_count = 0

        while True:
            if url in visited:
                raise StacSearchError("STAC pagination contains a URL cycle.")
            visited.add(url)
            page_count += 1
            if page_count > self.max_pages:
                raise StacSearchError("STAC search exceeded the page limit.")
            try:
                payload = self.transport.request(
                    method, url, body=body, max_bytes=self.max_page_bytes
                )
            except Exception:
                raise StacSearchError("STAC search page retrieval failed.") from None
            if not isinstance(payload, bytes):
                raise StacSearchError("STAC search transport must return bytes.")
            if len(payload) > self.max_page_bytes:
                raise StacSearchError("STAC search page exceeds the byte limit.")
            try:
                page = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
                raise StacSearchError("STAC search page is not valid JSON.") from None
            if not isinstance(page, dict) or page.get("type") != "FeatureCollection":
                raise StacSearchError("STAC search response must be a FeatureCollection.")
            features = page.get("features")
            if not isinstance(features, list):
                raise StacSearchError("STAC search response features must be an array.")
            for feature in features:
                if (
                    not isinstance(feature, dict)
                    or feature.get("type") != "Feature"
                    or not isinstance(feature.get("id"), str)
                    or not feature.get("id").strip()
                    or not isinstance(feature.get("stac_version"), str)
                ):
                    raise StacSearchError("STAC search returned an invalid Item feature.")
                item_count += 1
                if item_count > self.max_items:
                    raise StacSearchError("STAC search exceeded the Item limit.")
                yield feature

            links = page.get("links", [])
            if not isinstance(links, list):
                raise StacSearchError("STAC pagination links must be an array.")
            next_links = [
                link for link in links
                if isinstance(link, dict) and link.get("rel") == "next"
            ]
            if not next_links:
                return
            if len(next_links) != 1:
                raise StacSearchError("STAC page must contain at most one next link.")
            link = next_links[0]
            href = link.get("href")
            if not isinstance(href, str) or not href:
                raise StacSearchError("STAC next link requires an href.")
            url = self._validate_url(href)
            method_value = link.get("method", "GET")
            if not isinstance(method_value, str) or method_value.upper() not in {"GET", "POST"}:
                raise StacSearchError("STAC next link method must be GET or POST.")
            method = method_value.upper()
            next_body = link.get("body")
            if method == "GET":
                if next_body is not None:
                    raise StacSearchError("STAC GET pagination links cannot include a body.")
                body = None
            else:
                if next_body is not None and not isinstance(next_body, dict):
                    raise StacSearchError("STAC POST pagination body must be an object.")
                try:
                    body = json.dumps(
                        next_body or query, separators=(",", ":"), allow_nan=False
                    ).encode("utf-8")
                except (TypeError, ValueError):
                    raise StacSearchError("STAC POST pagination body is invalid.") from None

    @classmethod
    def _normalize_hosts(cls, values: set[str] | frozenset[str]) -> frozenset[str]:
        if not isinstance(values, (set, frozenset)) or not values:
            raise ValueError("A non-empty exact STAC host allowlist is required.")
        normalized: set[str] = set()
        for value in values:
            if (
                not isinstance(value, str)
                or not value.strip()
                or "*" in value
                or "/" in value
                or ":" in value
                or "@" in value
                or any(character.isspace() for character in value)
            ):
                raise ValueError("STAC hosts must be exact DNS hostnames.")
            normalized.add(value.strip().lower().rstrip("."))
        if "" in normalized:
            raise ValueError("STAC hosts must be exact DNS hostnames.")
        return frozenset(normalized)

    def _validate_url(self, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise StacSearchError("STAC endpoint and pagination hrefs must be URLs.")
        try:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            raise StacSearchError("STAC URL is malformed.") from None
        if (
            parsed.scheme.lower() != "https"
            or not host
            or host not in self.allowed_hosts
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise StacSearchError("STAC URL is not an allowlisted HTTPS resource.")
        return value

    @staticmethod
    def _build_query(
        *,
        bbox: list[float] | tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None,
        datetime: str | None,
        collections: list[str] | tuple[str, ...] | None,
        ids: list[str] | tuple[str, ...] | None,
        limit: int,
    ) -> dict[str, Any]:
        if bbox is not None and intersects is not None:
            raise StacSearchError("Specify bbox or intersects, not both.")
        query: dict[str, Any] = {}
        if bbox is not None:
            if not isinstance(bbox, (list, tuple)) or len(bbox) not in (4, 6):
                raise StacSearchError("bbox must contain four or six coordinates.")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in bbox
            ):
                raise StacSearchError("bbox coordinates must be finite numbers.")
            longitude_max = bbox[2] if len(bbox) == 4 else bbox[3]
            latitude_min, latitude_max = bbox[1], bbox[3 if len(bbox) == 4 else 4]
            if not -180 <= bbox[0] <= 180 or not -180 <= longitude_max <= 180:
                raise StacSearchError("bbox longitude coordinates must be within [-180, 180].")
            if not -90 <= latitude_min <= 90 or not -90 <= latitude_max <= 90:
                raise StacSearchError("bbox latitude coordinates must be within [-90, 90].")
            if latitude_min > latitude_max:
                raise StacSearchError("bbox minimum latitude must not exceed maximum latitude.")
            if len(bbox) == 6 and bbox[2] > bbox[5]:
                raise StacSearchError("bbox minimum height must not exceed maximum height.")
            # West > east is valid when a bbox crosses the antimeridian.
            query["bbox"] = list(bbox)
        if intersects is not None:
            if not isinstance(intersects, Mapping) or not isinstance(intersects.get("type"), str):
                raise StacSearchError("intersects must be a GeoJSON geometry object.")
            query["intersects"] = dict(intersects)
        if datetime is not None:
            if not isinstance(datetime, str) or not datetime.strip():
                raise StacSearchError("datetime must be a non-empty STAC interval string.")
            query["datetime"] = datetime
        for key, values in (("collections", collections), ("ids", ids)):
            if values is not None:
                if (
                    not isinstance(values, (list, tuple))
                    or not values
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                ):
                    raise StacSearchError(f"{key} must be a non-empty list of strings.")
                query[key] = list(values)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise StacSearchError("limit must be a positive integer.")
        query["limit"] = limit
        return query
