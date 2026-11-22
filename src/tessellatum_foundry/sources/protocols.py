"""Protocols shared by external spatial data source adapters."""

from __future__ import annotations

from typing import Iterator, Protocol

from .models import ExternalDataReference, SourceDescriptor


class SourceAdapter(Protocol):
    """Read external resources without requiring a Foundry-owned copy.

    Implementations must honor the requested chunk and byte bounds, close
    provider resources when iteration ends, and avoid exposing credentials in
    returned metadata or raised error messages.
    """

    def supports(self, reference: ExternalDataReference) -> bool: ...

    def describe(self, reference: ExternalDataReference) -> SourceDescriptor: ...

    def iter_chunks(
        self,
        reference: ExternalDataReference,
        *,
        chunk_size: int = 8 * 1024 * 1024,
        max_bytes: int | None = None,
    ) -> Iterator[bytes]: ...
