"""Allowlisted HTTPS source adapter with runtime-injected credentials."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from email.message import Message
from typing import Any
from urllib.parse import urlsplit

from .models import (
    ExternalDataReference,
    SourceDescriptor,
    SourceIntegrityError,
    SourceLimitExceeded,
)


class SourceAccessError(RuntimeError):
    """A remote source could not be accessed; details are intentionally redacted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward runtime credentials to an untrusted redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpSourceAdapter:
    """Stream allowlisted HTTPS resources without persisting credentials.

    The host allowlist is exact-match (no wildcard suffixes). Credentials are
    supplied for each request by a runtime callback. Redirects are rejected:
    callers must explicitly register the final resource host instead.
    """

    MAX_CHUNK_SIZE = 64 * 1024 * 1024
    _FORBIDDEN_HEADERS = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "proxy-authorization",
    }

    def __init__(
        self,
        *,
        allowed_hosts: Iterable[str],
        headers_resolver: Callable[[ExternalDataReference], Mapping[str, str]] | None = None,
        opener: Any | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        hosts = {host.strip().lower().rstrip(".") for host in allowed_hosts}
        if not hosts or any(not host for host in hosts):
            raise ValueError("At least one non-empty HTTPS host must be allowlisted.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.allowed_hosts = frozenset(hosts)
        self.headers_resolver = headers_resolver or (lambda _reference: {})
        self.opener = opener or urllib.request.build_opener(_NoRedirect()).open
        self.timeout_seconds = timeout_seconds

    def supports(self, reference: ExternalDataReference) -> bool:
        try:
            self._validate_uri(reference)
        except ValueError:
            return False
        return True

    def describe(self, reference: ExternalDataReference) -> SourceDescriptor:
        request = self._request(reference, method="HEAD")
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                headers = response.headers
                self._verify_etag(reference, headers)
                length = headers.get("Content-Length")
                byte_size = int(length) if length and length.isdigit() else None
                return SourceDescriptor(
                    reference=reference,
                    byte_size=byte_size,
                    modified_at=headers.get("Last-Modified"),
                    media_type=self._media_type(headers),
                )
        except SourceIntegrityError:
            raise
        except Exception as error:
            raise SourceAccessError("Remote source metadata could not be retrieved.") from None

    def iter_chunks(
        self,
        reference: ExternalDataReference,
        *,
        chunk_size: int = 8 * 1024 * 1024,
        max_bytes: int | None = None,
    ) -> Iterator[bytes]:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise TypeError("chunk_size must be an integer.")
        if chunk_size < 1 or chunk_size > self.MAX_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must be between 1 and {self.MAX_CHUNK_SIZE} bytes."
            )
        if max_bytes is not None and (
            isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0
        ):
            raise ValueError("max_bytes must be a non-negative integer or None.")

        request = self._request(reference, method="GET")
        digest = hashlib.sha256()
        total = 0
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                self._verify_etag(reference, response.headers)
                while True:
                    read_size = chunk_size
                    if max_bytes is not None:
                        read_size = min(chunk_size, max_bytes - total + 1)
                    chunk = response.read(read_size)
                    if not chunk:
                        break
                    if max_bytes is not None and total + len(chunk) > max_bytes:
                        raise SourceLimitExceeded(
                            f"Remote source exceeded the {max_bytes}-byte read limit."
                        )
                    total += len(chunk)
                    digest.update(chunk)
                    yield chunk
        except (SourceIntegrityError, SourceLimitExceeded):
            raise
        except Exception:
            raise SourceAccessError("Remote source bytes could not be retrieved.") from None

        expected = reference.checksum_sha256
        if expected is not None and digest.hexdigest() != expected:
            raise SourceIntegrityError(
                f"Remote source {reference.dataset_id!r} failed SHA-256 verification."
            )

    def _request(self, reference: ExternalDataReference, *, method: str) -> urllib.request.Request:
        self._validate_uri(reference)
        headers = self.headers_resolver(reference)
        if not isinstance(headers, Mapping):
            raise SourceAccessError("Runtime source credentials are unavailable.")
        safe_headers: dict[str, str] = {}
        for name, value in headers.items():
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or not name.strip()
                or any(char in name + value for char in "\r\n")
                or name.lower() in self._FORBIDDEN_HEADERS
            ):
                raise SourceAccessError("Runtime source headers are invalid.")
            safe_headers[name] = value
        try:
            return urllib.request.Request(reference.uri, headers=safe_headers, method=method)
        except Exception:
            raise SourceAccessError("Remote source request could not be constructed.") from None

    def _validate_uri(self, reference: ExternalDataReference) -> None:
        parsed = urlsplit(reference.uri)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or not host
            or host not in self.allowed_hosts
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Remote source URI is not an allowlisted HTTPS resource.")

    @staticmethod
    def _verify_etag(reference: ExternalDataReference, headers: Message) -> None:
        observed = headers.get("ETag")
        if reference.etag is not None and observed is not None and observed != reference.etag:
            raise SourceIntegrityError(
                f"Remote source {reference.dataset_id!r} changed ETag."
            )

    @staticmethod
    def _media_type(headers: Message) -> str | None:
        value = headers.get("Content-Type")
        return value.split(";", 1)[0].strip().lower() if value else None
