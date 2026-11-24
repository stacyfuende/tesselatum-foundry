"""Bounded HTTPS transport for STAC API search requests."""

from __future__ import annotations

import math
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit


class StacSearchTransportError(OSError):
    """A STAC search HTTP request failed or violated transport policy."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibStacSearchTransport:
    """Allowlisted HTTPS transport with bounded reads and runtime-only headers.

    The exact host allowlist is checked for every request, including pagination.
    Redirects are never followed. A header resolver may inject short-lived
    credentials at request time; its output is never persisted by this class.
    """

    _FORBIDDEN_HEADERS = frozenset(
        {
            "connection",
            "content-length",
            "host",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "proxy-connection",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
        }
    )

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | frozenset[str],
        timeout: float = 30.0,
        headers_resolver: Callable[[str, str], Mapping[str, str]] | None = None,
    ) -> None:
        if not isinstance(allowed_hosts, (set, frozenset)) or not allowed_hosts:
            raise ValueError("A non-empty exact STAC host allowlist is required.")
        hosts: set[str] = set()
        for host in allowed_hosts:
            if (
                not isinstance(host, str)
                or not host.strip()
                or "*" in host
                or "/" in host
                or ":" in host
                or "@" in host
                or any(character.isspace() for character in host)
            ):
                raise ValueError("STAC hosts must be exact DNS hostnames.")
            hosts.add(host.strip().lower().rstrip("."))
        if "" in hosts:
            raise ValueError("STAC hosts must be exact DNS hostnames.")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a positive finite number.")
        self.allowed_hosts = frozenset(hosts)
        self.timeout = float(timeout)
        self.headers_resolver = headers_resolver
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        max_bytes: int,
    ) -> bytes:
        """Perform one allowlisted request and return at most max_bytes."""
        if method not in {"GET", "POST"}:
            raise StacSearchTransportError("Unsupported STAC search HTTP method.")
        if method == "GET" and body is not None:
            raise StacSearchTransportError("STAC GET requests cannot include a body.")
        if method == "POST" and not isinstance(body, bytes):
            raise StacSearchTransportError("STAC POST requests require a byte body.")
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes < 1
        ):
            raise StacSearchTransportError("STAC response byte limit must be positive.")
        self._validate_url(url)

        headers = {
            "Accept": "application/geo+json, application/json",
            "Content-Type": "application/json",
        }
        if self.headers_resolver is not None:
            try:
                extra = self.headers_resolver(method, url)
            except Exception:
                raise StacSearchTransportError("STAC runtime credential resolution failed.") from None
            if not isinstance(extra, Mapping):
                raise StacSearchTransportError("STAC runtime headers must be a mapping.")
            for name, value in extra.items():
                if (
                    not isinstance(name, str)
                    or not isinstance(value, str)
                    or not name.strip()
                    or name.lower() in self._FORBIDDEN_HEADERS
                    or "\r" in name
                    or "\n" in name
                    or "\r" in value
                    or "\n" in value
                ):
                    raise StacSearchTransportError("STAC runtime header policy rejected a header.")
                headers[name] = value

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = response.read(max_bytes + 1)
        except urllib.error.HTTPError:
            raise StacSearchTransportError("STAC search HTTP request was rejected.") from None
        except Exception:
            raise StacSearchTransportError("STAC search HTTP request failed.") from None
        if len(payload) > max_bytes:
            raise StacSearchTransportError("STAC search response exceeds the byte limit.")
        return payload

    def _validate_url(self, url: str) -> None:
        if not isinstance(url, str) or not url:
            raise StacSearchTransportError("STAC request URL is required.")
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            raise StacSearchTransportError("STAC request URL is malformed.") from None
        if (
            parsed.scheme.lower() != "https"
            or host not in self.allowed_hosts
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise StacSearchTransportError("STAC request URL is not an allowlisted HTTPS resource.")
