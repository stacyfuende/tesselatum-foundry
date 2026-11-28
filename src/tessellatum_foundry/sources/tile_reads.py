"""One-at-a-time bounded retrieval of previously selected TIFF tiles."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .raster import BudgetedRasterRangeReader
from .tile_selection import RasterTileSelection


@dataclass(frozen=True, slots=True)
class RetrievedRasterTile:
    """A single encoded tile payload with its source range and checksum."""

    selection: RasterTileSelection
    payload: bytes
    sha256: str


def read_selected_tiff_tiles(
    reader: BudgetedRasterRangeReader,
    selections: Iterable[RasterTileSelection],
) -> Iterator[RetrievedRasterTile]:
    """Fetch selected tile ranges sequentially under the reader's shared budget.

    The iterator retains no collection of prior tile payloads. Consumers should
    process each yielded tile before requesting the next one. The range reader
    enforces the cumulative request/byte budget and strong-ETag source pin.
    """
    for selection in selections:
        payload = reader.read(
            offset=selection.byte_offset,
            length=selection.byte_length,
        )
        yield RetrievedRasterTile(
            selection=selection,
            payload=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
        )
