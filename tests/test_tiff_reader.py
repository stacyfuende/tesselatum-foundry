from __future__ import annotations

import struct

import pytest

from tessellatum_foundry.sources import (
    BudgetedRasterRangeReader,
    ExternalDataReference,
    SourceLimitExceeded,
    TiffFormatError,
    TiffRangeReader,
    TiffDirectory,
    assess_cog_structure,
)


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
            entries[index] = (
                struct.pack(endian + "HHI", tag, 4, 1)
                + struct.pack(endian + "I", pixel_offset)
            )
    header = (b"II" if endian == "<" else b"MM") + struct.pack(endian + "HI", 42, ifd_offset)
    directory = (
        struct.pack(endian + "H", len(entries))
        + b"".join(entries)
        + struct.pack(endian + "I", 0)
    )
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


def bigtiff():
    endian = "<"
    tags = [
        (256, 4, 1, (32,)),
        (257, 4, 1, (16,)),
        (258, 3, 1, (8,)),
        (259, 3, 1, (1,)),
        (273, 16, 1, (0,)),
        (277, 3, 1, (1,)),
        (278, 4, 1, (16,)),
        (279, 16, 1, (512,)),
        (339, 3, 1, (1,)),
        (33550, 12, 3, (2.0, 2.0, 0.0)),
        (33922, 12, 6, (0.0, 0.0, 0.0, 100.0, 200.0, 0.0)),
    ]
    ifd_offset = 16
    extra_start = ifd_offset + 8 + len(tags) * 20 + 8
    extra = bytearray()
    entries = []
    for tag, typ, count, values in tags:
        fmt = {3: "H", 4: "I", 12: "d", 16: "Q"}[typ]
        packed = struct.pack(endian + fmt * count, *values)
        if len(packed) <= 8:
            field = packed.ljust(8, b"\x00")
        else:
            field = struct.pack(endian + "Q", extra_start + len(extra))
            extra.extend(packed)
        entries.append(struct.pack(endian + "HHQ", tag, typ, count) + field)
    pixel_offset = extra_start + len(extra)
    for index, (tag, _typ, _count, _values) in enumerate(tags):
        if tag == 273:
            entries[index] = (
                struct.pack(endian + "HHQ", tag, 16, 1)
                + struct.pack(endian + "Q", pixel_offset)
            )
    header = b"II" + struct.pack(endian + "HHHQ", 43, 8, 0, ifd_offset)
    directory = (
        struct.pack(endian + "Q", len(entries))
        + b"".join(entries)
        + struct.pack(endian + "Q", 0)
    )
    return header + directory + bytes(extra) + b"\x00" * 512


def test_reads_bigtiff_header_and_first_directory():
    payload = bigtiff()
    tiff_reader, _ = reader(payload)

    result = tiff_reader.read(file_size=len(payload))

    assert result.layout.bigtiff is True
    assert result.layout.first_ifd_offset == 16
    assert result.metadata.width == 32
    assert result.metadata.height == 16
    assert result.strip_offsets[0] + result.strip_byte_counts[0] <= len(payload)


def directory_graph_tiff():
    """Create a main image IFD with one reduced-resolution SubIFD."""
    main_offset = 8
    main_count = 5
    main_size = 2 + main_count * 12 + 4
    overview_offset = main_offset + main_size
    overview_count = 4
    overview_size = 2 + overview_count * 12 + 4
    pixel_offset = overview_offset + overview_size
    main_tags = [
        (256, 4, 1, 64),
        (257, 4, 1, 64),
        (273, 4, 1, pixel_offset),
        (279, 4, 1, 256),
        (330, 13, 1, overview_offset),
    ]
    overview_tags = [
        (256, 4, 1, 16),
        (257, 4, 1, 16),
        (273, 4, 1, pixel_offset + 256),
        (279, 4, 1, 64),
    ]

    def encode_ifd(tags):
        entries = b"".join(
            struct.pack("<HHII", tag, typ, count, value)
            for tag, typ, count, value in tags
        )
        return struct.pack("<H", len(tags)) + entries + struct.pack("<I", 0)

    header = b"II" + struct.pack("<HI", 42, main_offset)
    return (
        header
        + encode_ifd(main_tags)
        + encode_ifd(overview_tags)
        + b"\x00" * 320
    )


def test_traverses_main_ifd_and_nested_subifd_with_bounds():
    payload = directory_graph_tiff()
    tiff_reader, _ = reader(payload)

    directories = tiff_reader.read_directory_index(
        file_size=len(payload), max_directories=2
    )

    assert len(directories) == 2
    assert directories[0].width == 64
    assert directories[0].height == 64
    assert directories[0].subifd_offsets == (directories[1].offset,)
    assert directories[1].width == 16
    assert directories[1].height == 16
    assert directories[1].block_offsets[0] > directories[0].block_offsets[0]


def test_directory_index_rejects_limit_and_subifd_cycle():
    payload = directory_graph_tiff()
    tiff_reader, _ = reader(payload)
    with pytest.raises(TiffFormatError, match="configured limit"):
        tiff_reader.read_directory_index(
            file_size=len(payload), max_directories=1
        )

    cyclic = bytearray(payload)
    # SubIFD offset points back to the main IFD.
    cyclic[8 + 2 + 4 * 12 + 8:8 + 2 + 5 * 12] = struct.pack("<I", 8)
    tiff_reader, _ = reader(bytes(cyclic))
    with pytest.raises(TiffFormatError, match="cycle or duplicate"):
        tiff_reader.read_directory_index(file_size=len(cyclic))


def test_directory_index_preserves_source_budget_errors():
    payload = classic_tiff()
    adapter = MemoryRanges(payload)
    reference = ExternalDataReference(
        provider="test",
        dataset_id="raster",
        uri="https://example.test/raster.tif",
        etag='"v1"',
    )
    bounded = BudgetedRasterRangeReader(
        adapter,
        reference,
        max_requests=1,
        max_total_bytes=1024,
        max_range_bytes=1024,
    )
    tiff_reader = TiffRangeReader(bounded)

    with pytest.raises(SourceLimitExceeded):
        tiff_reader.read_directory_index(file_size=len(payload))


def test_directory_index_follows_primary_ifd_chain():
    payload = bytearray(classic_tiff())
    first_ifd_size = struct.unpack_from("<H", payload, 8)[0] * 12 + 2 + 4
    second_offset = len(payload)
    next_pointer = 8 + first_ifd_size - 4
    struct.pack_into("<I", payload, next_pointer, second_offset)
    # Reuse the first IFD as a second primary-chain directory; its data ranges
    # remain valid and the directory offset is distinct.
    payload.extend(payload[8:8 + first_ifd_size])
    tiff_reader, _ = reader(bytes(payload))
    directories = tiff_reader.read_directory_index(file_size=len(payload))
    assert len(directories) == 2
    assert directories[0].next_ifd_offset == second_offset
    assert directories[1].offset == second_offset


def test_directory_index_rejects_tile_table_that_does_not_cover_grid():
    payload = bytearray(classic_tiff(tiled=True))
    entry_count = struct.unpack_from("<H", payload, 8)[0]
    for index in range(entry_count):
        entry = 10 + index * 12
        tag = struct.unpack_from("<H", payload, entry)[0]
        if tag == 256:
            struct.pack_into("<I", payload, entry + 8, 64)
            break
    tiff_reader, _ = reader(bytes(payload))
    with pytest.raises(TiffFormatError, match="tile table does not match"):
        tiff_reader.read_directory_index(file_size=len(payload))


def test_directory_index_exposes_tiled_directory_contract():
    payload = classic_tiff(tiled=True)
    tiff_reader, _ = reader(payload)
    directory = tiff_reader.read_directory_index(file_size=len(payload))[0]
    assert directory.tiled is True
    assert directory.tile_width == 32
    assert directory.tile_height == 16
    assert directory.samples_per_pixel == 1
    assert directory.planar_configuration == 1
    assert directory.compression == 1


def test_cog_structure_assessment_is_explicitly_conservative():
    primary = TiffDirectory(
        offset=8, width=1024, height=1024, tiled=True,
        block_offsets=(1000,), block_byte_counts=(100,),
        subifd_offsets=(300,), next_ifd_offset=0,
        tile_width=256, tile_height=256, samples_per_pixel=3,
        planar_configuration=1, compression=7, new_subfile_type=0,
    )
    overview = TiffDirectory(
        offset=300, width=256, height=256, tiled=True,
        block_offsets=(2000,), block_byte_counts=(100,),
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=256, tile_height=256, samples_per_pixel=3,
        planar_configuration=1, compression=7, new_subfile_type=1,
    )
    result = assess_cog_structure((primary, overview))
    assert result.candidate is True
    assert not result.issues
    assert "Primary directory is tiled." in result.checks
    assert "Directory 1 is marked reduced-resolution." in result.checks


def test_cog_structure_assessment_rejects_non_overview_directory():
    primary = TiffDirectory(
        offset=8, width=100, height=100, tiled=True,
        block_offsets=(1000,), block_byte_counts=(100,),
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=64, tile_height=64, samples_per_pixel=1,
        planar_configuration=1, compression=1, new_subfile_type=0,
    )
    same_size = TiffDirectory(
        offset=200, width=100, height=100, tiled=False,
        block_offsets=(1200,), block_byte_counts=(100,),
        subifd_offsets=(), next_ifd_offset=0,
        tile_width=None, tile_height=None, samples_per_pixel=1,
        planar_configuration=1, compression=1, new_subfile_type=0,
    )
    result = assess_cog_structure((primary, same_size))
    assert result.candidate is False
    assert any("not smaller" in issue for issue in result.issues)
    assert any("not marked" in issue for issue in result.issues)
    assert any("strip-based" in issue for issue in result.issues)
