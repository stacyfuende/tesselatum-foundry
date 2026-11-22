"""Provider-neutral external data reference value objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceIntegrityError(RuntimeError):
    """Raised when an external source does not match its declared identity."""


class SourceLimitExceeded(RuntimeError):
    """Raised when a source read exceeds its declared byte budget."""


@dataclass(frozen=True, slots=True)
class ExternalDataReference:
    """A locator and provenance hint for data whose custody remains external.

    Credentials and expiring signed query parameters must not be embedded in
    the URI. Supply access through the adapter's runtime configuration.
    """

    provider: str
    dataset_id: str
    uri: str
    resource_id: str | None = None
    version: str | None = None
    etag: str | None = None
    checksum_sha256: str | None = None
    media_type: str | None = None
    retrieved_at: str | None = None
    selection: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.dataset_id.strip():
            raise ValueError("provider and dataset_id must be non-empty.")
        parsed = urlsplit(self.uri)
        if not parsed.scheme:
            raise ValueError("uri must be an absolute resource URI.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("credentials must not be embedded in source URIs.")
        if parsed.query or parsed.fragment:
            raise ValueError(
                "query parameters and fragments belong in selection or adapter configuration."
            )
        if self.checksum_sha256 is not None and not _SHA256.fullmatch(
            self.checksum_sha256
        ):
            raise ValueError("checksum_sha256 must be a lowercase SHA-256 hex digest.")
        if not isinstance(self.selection, Mapping):
            raise TypeError("selection must be a mapping.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible provenance representation."""
        result: dict[str, Any] = {
            "provider": self.provider,
            "dataset_id": self.dataset_id,
            "uri": self.uri,
        }
        for key in (
            "resource_id",
            "version",
            "etag",
            "checksum_sha256",
            "media_type",
            "retrieved_at",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.selection:
            result["selection"] = dict(self.selection)
        return result


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """Metadata observed by an adapter without taking custody of source bytes."""

    reference: ExternalDataReference
    byte_size: int | None = None
    modified_at: str | None = None
    media_type: str | None = None
