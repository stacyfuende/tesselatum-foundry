"""Allowlisted HTTPS source adapter with runtime-injected credentials."""

from __future__ import annotations

import hashlib
import re
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
        except Exception:
            raise SourceAccessError("Remote source metadata could not be retrieved.") from None

    def read_range(
        self,
        reference: ExternalDataReference,
        *,
        offset: int,
        length: int,
        max_range_bytes: int = 16 * 1024 * 1024,
    ) -> bytes:
        """Read one exact byte range without falling back to a full-object GET.

        A range is accepted only when the server returns HTTP 206 with an
        exact Content-Range and byte count. If an ETag is known it is sent as
        If-Match and verified again on the response. This is the transport
        primitive needed by COG readers; it does not parse TIFF metadata.
        """
        for name, value in (("offset", offset), ("length", length),
                            ("max_range_bytes", max_range_bytes)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
        if offset < 0 or length < 1 or max_range_bytes < 1:
            raise ValueError("offset must be non-negative and range limits positive.")
        if length > max_range_bytes:
            raise SourceLimitExceeded(
                f"Requested range exceeds the {max_range_bytes}-byte range limit."
            )
        end = offset + length - 1
        range_headers = {
            "Range": f"bytes={offset}-{end}",
            "Accept-Encoding": "identity",
        }
        if reference.etag is not None:
            range_headers["If-Match"] = reference.etag
        request = self._request(reference, method="GET", extra_headers=range_headers)
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                if status != 206:
                    raise SourceIntegrityError(
                        "Remote source did not honor the requested byte range."
                    )
                content_encoding = response.headers.get("Content-Encoding", "identity")
                if content_encoding.lower() not in {"", "identity"}:
                    raise SourceIntegrityError(
                        "Remote source applied content encoding to a byte range."
                    )
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                if (
                    match is None
                    or int(match.group(1)) != offset
                    or int(match.group(2)) != end
                    or int(match.group(3)) <= end
                ):
                    raise SourceIntegrityError(
                        "Remote source returned an unexpected Content-Range."
                    )
                self._verify_etag(reference, response.headers)
                content_length = response.headers.get("Content-Length")
                if content_length is not None and content_length != str(length):
                    raise SourceIntegrityError(
                        "Remote source returned an unexpected range Content-Length."
                    )
                payload = response.read(length + 1)
                if len(payload) != length:
                    raise SourceIntegrityError(
                        "Remote source returned an incomplete or oversized byte range."
                    )
                return payload
        except (SourceIntegrityError, SourceLimitExceeded):
            raise
        except urllib.error.HTTPError as error:
            if error.code == 412:
                raise SourceIntegrityError(
                    "Remote source validator no longer matches the requested version."
                ) from None
            raise SourceAccessError(
                "Remote source byte range could not be retrieved."
            ) from None
        except Exception:
            raise SourceAccessError(
                "Remote source byte range could not be retrieved."
            ) from None

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
                content_length = response.headers.get("Content-Length")
                expected_size = (
                    int(content_length)
                    if content_length and content_length.isdigit()
                    else None
                )
                if (
                    max_bytes is not None
                    and expected_size is not None
                    and expected_size > max_bytes
                ):
                    raise SourceLimitExceeded(
                        f"Remote source exceeds the {max_bytes}-byte read limit."
                    )
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
                if expected_size is not None and total != expected_size:
                    raise SourceIntegrityError(
                        f"Remote source {reference.dataset_id!r} size changed during retrieval."
                    )
        except (SourceIntegrityError, SourceLimitExceeded):
            raise
        except Exception:
            raise SourceAccessError("Remote source bytes could not be retrieved.") from None

        expected = reference.checksum_sha256
        if expected is not None and digest.hexdigest() != expected:
            raise SourceIntegrityError(
                f"Remote source {reference.dataset_id!r} failed SHA-256 verification."
            )

    def _request(
        self,
        reference: ExternalDataReference,
        *,
        method: str,
        extra_headers: Mapping[str, str] | None = None,
    ) -> urllib.request.Request:
        self._validate_uri(reference)
        try:
            headers = self.headers_resolver(reference)
        except Exception:
            raise SourceAccessError("Runtime source credentials are unavailable.") from None
        if not isinstance(headers, Mapping):
            raise SourceAccessError("Runtime source credentials are unavailable.")
        safe_headers: dict[str, str] = {}
        combined_headers = dict(headers)
        if extra_headers:
            combined_headers.update(extra_headers)
        for name, value in combined_headers.items():
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
        if reference.etag is not None and observed != reference.etag:
            raise SourceIntegrityError(
                f"Remote source {reference.dataset_id!r} ETag is missing or changed."
            )

    @staticmethod
    def _media_type(headers: Message) -> str | None:
        value = headers.get("Content-Type")
        return value.split(";", 1)[0].strip().lower() if value else None
