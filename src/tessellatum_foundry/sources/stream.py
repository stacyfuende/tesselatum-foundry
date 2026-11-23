"""Compose external byte adapters, incremental readers and bounded batches."""

from __future__ import annotations

from collections.abc import Iterator

from .batches import FeatureBatch, iter_feature_batches
from .models import ExternalDataReference
from .protocols import FeatureReader, SourceAdapter


class ExternalFeatureStreamError(ValueError):
    """Raised when a source cannot be decoded by the selected feature reader."""


def iter_external_feature_batches(
    reference: ExternalDataReference,
    *,
    adapter: SourceAdapter,
    reader: FeatureReader,
    chunk_size: int = 8 * 1024 * 1024,
    max_source_bytes: int | None = None,
    max_batch_features: int = 1_000,
    max_batch_bytes: int = 8 * 1024 * 1024,
) -> Iterator[FeatureBatch]:
    """Stream an external resource through a reader into bounded feature batches.

    Source bytes are not copied into Artifact storage. The adapter owns source
    access and integrity checks; the reader owns incremental format decoding;
    the batcher owns worker payload bounds and batch checksums.
    """
    if not adapter.supports(reference):
        raise ExternalFeatureStreamError(
            f"No source adapter support for provider {reference.provider!r}."
        )
    descriptor = adapter.describe(reference)
    media_type = reference.media_type or descriptor.media_type
    if not media_type:
        raise ExternalFeatureStreamError(
            "External source media_type must be declared or discoverable."
        )
    if media_type not in reader.supported_media_types:
        raise ExternalFeatureStreamError(
            f"Feature reader does not support media type {media_type!r}."
        )

    chunks = adapter.iter_chunks(
        reference,
        chunk_size=chunk_size,
        max_bytes=max_source_bytes,
    )
    features = reader.iter_features(chunks, selection=reference.selection)
    yield from iter_feature_batches(
        features,
        max_features=max_batch_features,
        max_bytes=max_batch_bytes,
    )
