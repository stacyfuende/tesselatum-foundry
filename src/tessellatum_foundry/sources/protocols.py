"""Protocols shared by external spatial data source adapters."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Protocol

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



class FeatureReader(Protocol):
    """Incrementally decode a source byte stream into individual features.

    Readers must bound any internal buffering, preserve source order, reject
    malformed records, and never silently skip invalid feature records.
    Selection is explicit; unsupported selection must be rejected rather than
    ignored. Implementations must not retain the complete source in memory.
    """

    supported_media_types: tuple[str, ...]

    def iter_features(
        self,
        chunks: Iterable[bytes],
        *,
        selection: Mapping[str, object],
    ) -> Iterator[Mapping[str, object]]:
        """Yield decoded features from a bounded byte stream."""
        ...
