from __future__ import annotations

import struct

import pytest

from tessellatum_foundry.sources import BudgetedRasterRangeReader, ExternalDataReference
from tessellatum_foundry.sources.tiff import TiffFormatError, TiffRangeReader


class MemoryRanges:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def read_range(self, reference, *, offset, length, max_range_bytes):
        self.calls.append((offset, length))
        return self.payload[offset:offset + length]


def classic_tiff(*, endian="<", tiled=False):
    """Build a small georeferenced classic TIFF with one image directory."""
    tags = [
        (256, 4, 1, (32,)),
        (257, 4, 1, (16,)),
        (258, 3, 1, (8,)),
        (259, 3, 1, (1,)),
        (262, 3, 1, (1,)),
        (277, 3, 1, (1,)),
        (278 if not tiled else 323, 4, 1, (16 if not tiled else 16,)),
        (339, 3, 1, (1,)),
        (33550, 12, 3, (2.0, 2.0, 0.0)),
        (33922, 12, 6, (0.0, 0.0, 0.0, 100.0, 200.0, 0.0)),
    ]
    if tiled:
        tags.extend([(322, 4, 1, (32,))])
        offset_tag, count_tag = 324, 325
    else:
        offset_tag, count_tag = 273, 279
    tags.extend([(offset_tag, 4, 1, (0,)), (count_tag, 4, 1, (512,))])
    tags.sort()
    ifd_offset = 8
    extra_start = ifd_offset + 2 + len(tags) * 12 + 4
    extra = bytearray()
    entries = []
    for tag, typ, count, values in tags:
        fmt = {3: "H", 4: "I", 12: "d"}[typ]
        packed = struct.pack(endian + fmt * count, *values)
        if len(packed) <= 4:
            field = packed.ljust(4, b"\x00")
        else:
            field = struct.pack(endian + "I", extra_start + len(extra))
            extra.extend(packed)
        entries.append(struct.pack(endian + "HHI", tag, typ, count) + field)
    pixel_offset = extra_start + len(extra)
    # Patch the strip/tile offset to a valid byte immediately after metadata.
    for index, (tag, _typ, _count, _values) in enumerate(tags):
        if tag == offset_tag:
            entries[index] = struct.pack(endian + "HHI", tag, 4, 1) + struct.pack(endian + "I", pixel_offset)
    header = (b"II" if endian == "<" else b"MM") + struct.pack(endian + "HI", 42, ifd_offset)
    directory = struct.pack(endian + "H", len(entries)) + b"".join(entries) + struct.pack(endian + "I", 0)
    return header + directory + bytes(extra) + b"\x00" * 512


def reader(payload):
    adapter = MemoryRanges(payload)
    reference = ExternalDataReference(
        provider="test", dataset_id="raster", uri="https://example.test/raster.tif", etag='"v1"'
    )
    return TiffRangeReader(
        BudgetedRasterRangeReader(
            adapter, reference, max_requests=32, max_total_bytes=1024 * 1024
        )
    ), adapter


@pytest.mark.parametrize("endian", ["<", ">"])
def test_reads_classic_tiff_georeferencing_and_strips(endian):
    payload = classic_tiff(endian=endian)
    tiff_reader, adapter = reader(payload)

    result = tiff_reader.read(file_size=len(payload))

    assert result.layout.bigtiff is False
    assert result.layout.byte_order == ("little" if endian == "<" else "big")
    assert result.metadata.width == 32
    assert result.metadata.height == 16
    assert result.metadata.dtypes == ("uint8",)
    assert result.metadata.transform == (100.0, 2.0, 0.0, 200.0, 0.0, -2.0)
    assert result.tiled is False
    assert result.strip_offsets[0] + result.strip_byte_counts[0] <= len(payload)
    assert len(adapter.calls) <= 8


def test_rejects_invalid_tiff_header_and_directory_bounds():
    payload = b"NO" + b"\x00" * 64
    tiff_reader, _ = reader(payload)
    with pytest.raises(TiffFormatError, match="byte-order"):
        tiff_reader.read(file_size=len(payload))

    truncated = classic_tiff()[:20]
    tiff_reader, _ = reader(truncated)
    with pytest.raises(TiffFormatError):
        tiff_reader.read(file_size=len(truncated))


def test_rejects_unsupported_sample_representation():
    payload = bytearray(classic_tiff())
    # First BitsPerSample entry is at IFD entry 2; replace it with 12 bits.
    bits_entry = 8 + 2 + 2 * 12
    payload[bits_entry + 8:bits_entry + 10] = struct.pack("<H", 12)
    tiff_reader, _ = reader(bytes(payload))
    with pytest.raises(TiffFormatError, match="Unsupported TIFF sample"):
        tiff_reader.read(file_size=len(payload))
