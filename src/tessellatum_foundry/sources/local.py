"""Local-file adapter for external data references."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlsplit

from .models import (
    ExternalDataReference,
    SourceDescriptor,
    SourceIntegrityError,
    SourceLimitExceeded,
)


class LocalFileSourceAdapter:
    """Describe and stream local files without copying them into Artifact storage."""

    MAX_CHUNK_SIZE = 64 * 1024 * 1024

    def supports(self, reference: ExternalDataReference) -> bool:
        parsed = urlsplit(reference.uri)
        return parsed.scheme == "file" and parsed.netloc in ("", "localhost")

    def _path(self, reference: ExternalDataReference) -> Path:
        if not self.supports(reference):
            raise ValueError("LocalFileSourceAdapter only supports local file:// URIs.")
        path = Path(unquote(urlsplit(reference.uri).path)).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"External source file was not found: {path.name}")
        return path

    def describe(self, reference: ExternalDataReference) -> SourceDescriptor:
        path = self._path(reference)
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
        return SourceDescriptor(
            reference=reference,
            byte_size=stat.st_size,
            modified_at=modified,
            media_type=reference.media_type,
        )

    def iter_chunks(
        self,
        reference: ExternalDataReference,
        *,
        chunk_size: int = 8 * 1024 * 1024,
        max_bytes: int | None = None,
    ) -> Iterator[bytes]:
        """Yield bounded chunks and verify an optional checksum at EOF.

        A checksum failure is raised after the consumer has read the stream.
        Callers must not publish outputs until iteration completes successfully.
        """
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

        path = self._path(reference)
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as stream:
            while True:
                read_size = chunk_size
                if max_bytes is not None:
                    remaining = max_bytes - total
                    read_size = min(chunk_size, remaining + 1)
                chunk = stream.read(read_size)
                if not chunk:
                    break
                if max_bytes is not None and total + len(chunk) > max_bytes:
                    raise SourceLimitExceeded(
                        f"External source exceeded the {max_bytes}-byte read limit."
                    )
                total += len(chunk)
                digest.update(chunk)
                yield chunk

        expected = reference.checksum_sha256
        if expected is not None and digest.hexdigest() != expected:
            raise SourceIntegrityError(
                f"External source {reference.dataset_id!r} failed SHA-256 verification."
            )
