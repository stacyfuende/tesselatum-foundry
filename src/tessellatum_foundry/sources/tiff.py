"""Bounded classic TIFF/BigTIFF directory reader for raster metadata.

This module reads TIFF headers and the first image file directory (IFD) using
byte ranges only. It deliberately does not claim full COG conformance or decode
pixel blocks.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .raster import BudgetedRasterRangeReader, RasterMetadata


class TiffFormatError(ValueError):
    """The TIFF header or first image directory is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class TiffLayout:
    byte_order: str
    bigtiff: bool
    first_ifd_offset: int
    file_size: int


@dataclass(frozen=True, slots=True)
class TiffDirectory:
    """One bounded TIFF directory and its image-block byte ranges."""

    offset: int
    width: int
    height: int
    tiled: bool
    block_offsets: tuple[int, ...]
    block_byte_counts: tuple[int, ...]
    subifd_offsets: tuple[int, ...]
    next_ifd_offset: int


@dataclass(frozen=True, slots=True)
class TiffRaster:
    layout: TiffLayout
    metadata: RasterMetadata
    compression: int
    tiled: bool
    tile_offsets: tuple[int, ...]
    tile_byte_counts: tuple[int, ...]
    strip_offsets: tuple[int, ...]
    strip_byte_counts: tuple[int, ...]


_TYPE_FORMATS = {
    1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4),
    5: ("II", 8), 6: ("b", 1), 7: ("B", 1), 8: ("h", 2),
    9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8),
    13: ("I", 4), 16: ("Q", 8), 17: ("q", 8), 18: ("Q", 8),
}


class TiffRangeReader:
    """Read bounded TIFF metadata through an ETag-pinned range reader."""

    def __init__(
        self,
        source: BudgetedRasterRangeReader,
        *,
        max_ifd_entries: int = 4096,
        max_tag_bytes: int = 1024 * 1024,
    ) -> None:
        if (
            isinstance(max_ifd_entries, bool)
            or not isinstance(max_ifd_entries, int)
            or max_ifd_entries < 1
        ):
            raise ValueError("max_ifd_entries must be a positive integer.")
        if (
            isinstance(max_tag_bytes, bool)
            or not isinstance(max_tag_bytes, int)
            or max_tag_bytes < 1
        ):
            raise ValueError("max_tag_bytes must be a positive integer.")
        self.source = source
        self.max_ifd_entries = max_ifd_entries
        self.max_tag_bytes = max_tag_bytes

    def read_directory_index(
        self, *, file_size: int, max_directories: int = 256
    ) -> tuple[TiffDirectory, ...]:
        """Traverse the primary IFD chain and nested SubIFDs with hard bounds."""
        if (
            isinstance(max_directories, bool)
            or not isinstance(max_directories, int)
            or max_directories < 1
        ):
            raise ValueError("max_directories must be a positive integer.")
        endian, big, first_offset, count_size, entry_size, next_size, inline_size, offset_fmt = (
            self._header(file_size)
        )
        pending = [first_offset]
        visited: set[int] = set()
        directories: list[TiffDirectory] = []
        while pending:
            offset = pending.pop(0)
            if offset in visited:
                raise TiffFormatError("TIFF directory graph contains a cycle or duplicate reference.")
            if len(directories) >= max_directories:
                raise TiffFormatError("TIFF directory graph exceeds its configured limit.")
            visited.add(offset)
            count_fmt = "Q" if big else "H"
            raw_count = self._read_checked(offset, count_size, file_size)
            count = struct.unpack(endian + count_fmt, raw_count)[0]
            if count < 1 or count > self.max_ifd_entries:
                raise TiffFormatError("TIFF directory entry count is empty or exceeds its limit.")
            entries_start = offset + count_size
            size = count * entry_size + next_size
            raw = self._read_checked(entries_start, size, file_size)
            tags: dict[int, tuple[int, int, bytes]] = {}
            for index in range(count):
                entry = raw[index * entry_size:(index + 1) * entry_size]
                if big:
                    tag, typ, value_count = struct.unpack(endian + "HHQ", entry[:12])
                    value_field = entry[12:20]
                else:
                    tag, typ, value_count = struct.unpack(endian + "HHI", entry[:8])
                    value_field = entry[8:12]
                if tag in tags:
                    raise TiffFormatError(f"TIFF directory contains duplicate tag {tag}.")
                if typ not in _TYPE_FORMATS:
                    continue
                unit = _TYPE_FORMATS[typ][1]
                byte_count = value_count * unit
                if byte_count > self.max_tag_bytes:
                    raise TiffFormatError(f"TIFF tag {tag} exceeds the configured metadata limit.")
                if byte_count <= inline_size:
                    payload = value_field[:byte_count]
                else:
                    value_offset = struct.unpack(endian + offset_fmt, value_field)[0]
                    payload = self._read_checked(value_offset, byte_count, file_size)
                tags[tag] = (typ, value_count, payload)

            def integer_values(tag: int) -> tuple[int, ...]:
                item = tags.get(tag)
                if item is None:
                    return ()
                typ, value_count, payload = item
                if typ not in (3, 4, 13, 16, 18):
                    raise TiffFormatError(f"TIFF tag {tag} must contain unsigned integer offsets.")
                fmt = _TYPE_FORMATS[typ][0]
                return tuple(int(value) for value in struct.unpack(endian + fmt * value_count, payload))

            width_values = integer_values(256)
            height_values = integer_values(257)
            if not width_values or not height_values:
                raise TiffFormatError("TIFF directory is missing image dimensions.")
            width, height = width_values[0], height_values[0]
            tiled = 322 in tags or 323 in tags
            if tiled:
                if 322 not in tags or 323 not in tags:
                    raise TiffFormatError("Tiled TIFF directory must declare both tile dimensions.")
                block_offsets = integer_values(324)
                block_counts = integer_values(325)
            else:
                block_offsets = integer_values(273)
                block_counts = integer_values(279)
            if not block_offsets or len(block_offsets) != len(block_counts):
                raise TiffFormatError("TIFF directory block offsets and byte counts are incomplete.")
            for block_offset, block_count in zip(block_offsets, block_counts):
                if block_count < 1 or block_offset + block_count > file_size:
                    raise TiffFormatError("TIFF block byte range is outside the declared file.")
            subifds = integer_values(330)
            next_offset = struct.unpack(
                endian + ("Q" if big else "I"), raw[count * entry_size:count * entry_size + next_size]
            )[0]
            if next_offset:
                pending.append(next_offset)
            pending.extend(subifds)
            directories.append(
                TiffDirectory(
                    offset, width, height, tiled, block_offsets, block_counts, subifds, next_offset
                )
            )
        return tuple(directories)

    def _header(self, file_size: int):
        if isinstance(file_size, bool) or not isinstance(file_size, int) or file_size < 8:
            raise TiffFormatError("TIFF file size must be an integer of at least eight bytes.")
        header = self.source.read(offset=0, length=min(16, file_size))
        if header[:2] == b"II":
            endian = "<"
        elif header[:2] == b"MM":
            endian = ">"
        else:
            raise TiffFormatError("TIFF byte-order marker is invalid.")
        magic = struct.unpack(endian + "H", header[2:4])[0]
        if magic == 42:
            big = False
            if len(header) < 8:
                raise TiffFormatError("Classic TIFF header is truncated.")
            first_offset = struct.unpack(endian + "I", header[4:8])[0]
            count_size, entry_size, next_size, inline_size, offset_fmt = 2, 12, 4, 4, "I"
        elif magic == 43:
            if len(header) < 16:
                raise TiffFormatError("BigTIFF header is truncated.")
            offset_size = struct.unpack(endian + "H", header[4:6])[0]
            if offset_size != 8 or header[6:8] != b"\x00\x00":
                raise TiffFormatError("BigTIFF offset-size declaration is unsupported.")
            big = True
            first_offset = struct.unpack(endian + "Q", header[8:16])[0]
            count_size, entry_size, next_size, inline_size, offset_fmt = 8, 20, 8, 8, "Q"
        else:
            raise TiffFormatError("TIFF magic number is neither 42 nor 43.")
        if first_offset < (16 if big else 8) or first_offset >= file_size:
            raise TiffFormatError("First TIFF IFD offset is outside the file.")
        return endian, big, first_offset, count_size, entry_size, next_size, inline_size, offset_fmt

    def read(self, *, file_size: int) -> TiffRaster:
        if isinstance(file_size, bool) or not isinstance(file_size, int) or file_size < 8:
            raise TiffFormatError("TIFF file size must be an integer of at least eight bytes.")
        header = self.source.read(offset=0, length=min(16, file_size))
        if header[:2] == b"II":
            endian = "<"
            byte_order = "little"
        elif header[:2] == b"MM":
            endian = ">"
            byte_order = "big"
        else:
            raise TiffFormatError("TIFF byte-order marker is invalid.")

        magic = struct.unpack(endian + "H", header[2:4])[0]
        if magic == 42:
            big = False
            if len(header) < 8:
                raise TiffFormatError("Classic TIFF header is truncated.")
            ifd_offset = struct.unpack(endian + "I", header[4:8])[0]
            count_size, entry_size, next_size, inline_size = 2, 12, 4, 4
            count_fmt, offset_fmt = "H", "I"
        elif magic == 43:
            big = True
            offset_size = struct.unpack(endian + "H", header[4:6])[0]
            if len(header) < 16 or offset_size != 8 or header[6:8] != b"\x00\x00":
                raise TiffFormatError("BigTIFF offset-size declaration is unsupported.")
            ifd_offset = struct.unpack(endian + "Q", header[8:16])[0]
            count_size, entry_size, next_size, inline_size = 8, 20, 8, 8
            count_fmt, offset_fmt = "Q", "Q"
        else:
            raise TiffFormatError("TIFF magic number is neither 42 nor 43.")

        if ifd_offset < (16 if big else 8) or ifd_offset >= file_size:
            raise TiffFormatError("First TIFF IFD offset is outside the file.")
        count_raw = self._read_checked(ifd_offset, count_size, file_size)
        entry_count = struct.unpack(endian + count_fmt, count_raw)[0]
        if entry_count < 1 or entry_count > self.max_ifd_entries:
            raise TiffFormatError("TIFF IFD entry count is empty or exceeds its configured limit.")
        entries_start = ifd_offset + count_size
        directory_size = entry_count * entry_size + next_size
        if entries_start + directory_size > file_size:
            raise TiffFormatError("TIFF IFD extends beyond the declared file size.")
        raw = self._read_checked(entries_start, directory_size, file_size)
        tags: dict[int, tuple[int, int, bytes]] = {}
        for index in range(entry_count):
            entry = raw[index * entry_size:(index + 1) * entry_size]
            if big:
                tag, typ, count = struct.unpack(endian + "HHQ", entry[:12])
                value_field = entry[12:20]
            else:
                tag, typ, count = struct.unpack(endian + "HHI", entry[:8])
                value_field = entry[8:12]
            if typ not in _TYPE_FORMATS:
                continue
            _, unit = _TYPE_FORMATS[typ]
            byte_count = count * unit
            if byte_count > self.max_tag_bytes:
                raise TiffFormatError(f"TIFF tag {tag} exceeds the configured metadata limit.")
            if byte_count <= inline_size:
                payload = value_field[:byte_count]
            else:
                value_offset = struct.unpack(endian + offset_fmt, value_field)[0]
                payload = self._read_checked(value_offset, byte_count, file_size)
            if tag in tags:
                raise TiffFormatError(f"TIFF IFD contains duplicate tag {tag}.")
            tags[tag] = (typ, count, payload)

        def values(tag: int, default=()):
            item = tags.get(tag)
            if item is None:
                return default
            typ, count, payload = item
            fmt, unit = _TYPE_FORMATS[typ]
            if typ == 2:
                return (payload.rstrip(b"\x00").decode("ascii", "strict"),)
            if typ in (5, 10):
                signed = typ == 10
                pair_fmt = "ii" if signed else "II"
                pairs = [struct.unpack(endian + pair_fmt, payload[i:i + 8])
                         for i in range(0, count * unit, 8)]
                return tuple(a / b for a, b in pairs if b != 0)
            if typ == 7:
                return tuple(payload)
            return struct.unpack(endian + fmt * count, payload)

        width = int(values(256, (0,))[0])
        height = int(values(257, (0,))[0])
        if width < 1 or height < 1:
            raise TiffFormatError("TIFF image width and height must be present and positive.")
        samples = int(values(277, (1,))[0])
        bits = tuple(int(v) for v in values(258, (1,)))
        if len(bits) == 1 and samples > 1:
            bits *= samples
        sample_formats = tuple(int(v) for v in values(339, (1,)))
        if len(sample_formats) == 1 and samples > 1:
            sample_formats *= samples
        if len(bits) != samples or len(sample_formats) != samples:
            raise TiffFormatError("TIFF sample metadata does not align with SamplesPerPixel.")
        dtypes = tuple(self._dtype(bit, fmt) for bit, fmt in zip(bits, sample_formats))
        compression = int(values(259, (1,))[0])
        tiled = 322 in tags or 323 in tags
        if tiled:
            if 322 not in tags or 323 not in tags:
                raise TiffFormatError("Tiled TIFF must declare both tile dimensions.")
            block_width = int(values(322)[0])
            block_height = int(values(323)[0])
            offsets = tuple(int(v) for v in values(324))
            counts = tuple(int(v) for v in values(325))
            if not offsets or len(offsets) != len(counts):
                raise TiffFormatError("TIFF tile offsets and byte counts are incomplete.")
            block_shapes = tuple((block_height, block_width) for _ in range(samples))
            tile_offsets, tile_counts = offsets, counts
            strip_offsets = strip_counts = ()
        else:
            rows_per_strip = int(values(278, (height,))[0])
            offsets = tuple(int(v) for v in values(273))
            counts = tuple(int(v) for v in values(279))
            if not offsets or len(offsets) != len(counts):
                raise TiffFormatError("TIFF strip offsets and byte counts are incomplete.")
            block_shapes = tuple((min(rows_per_strip, height), width) for _ in range(samples))
            strip_offsets, strip_counts = offsets, counts
            tile_offsets = tile_counts = ()
        for offset, count in zip(tile_offsets or strip_offsets, tile_counts or strip_counts):
            if offset < 0 or count < 1 or offset + count > file_size:
                raise TiffFormatError("TIFF tile or strip byte range is outside the file.")

        transform = self._transform(values, width, height)
        nodata_text = values(42113, ())
        nodata = self._nodata(nodata_text[0], samples) if nodata_text else (None,) * samples
        metadata = RasterMetadata(
            width=width,
            height=height,
            band_count=samples,
            dtypes=dtypes,
            transform=transform,
            nodata=nodata,
            block_shapes=block_shapes,
            driver="GTiff",
        )
        return TiffRaster(
            TiffLayout(byte_order, big, ifd_offset, file_size),
            metadata,
            compression,
            tiled,
            tile_offsets,
            tile_counts,
            strip_offsets,
            strip_counts,
        )

    def _read_checked(self, offset: int, length: int, file_size: int) -> bytes:
        if offset < 0 or length < 1 or offset + length > file_size:
            raise TiffFormatError("TIFF metadata range is outside the declared file.")
        return self.source.read(offset=offset, length=length)

    @staticmethod
    def _dtype(bits: int, sample_format: int) -> str:
        names = {
            (1, 1): "uint1", (8, 1): "uint8", (16, 1): "uint16",
            (32, 1): "uint32", (64, 1): "uint64", (8, 2): "int8",
            (16, 2): "int16", (32, 2): "int32", (64, 2): "int64",
            (32, 3): "float32", (64, 3): "float64",
        }
        try:
            return names[(bits, sample_format)]
        except KeyError as error:
            raise TiffFormatError(
                f"Unsupported TIFF sample representation: {bits} bits, format {sample_format}."
            ) from error

    @staticmethod
    def _transform(values, width: int, height: int):
        matrix = values(34264, ())
        if matrix:
            if len(matrix) != 16:
                raise TiffFormatError("ModelTransformationTag must contain 16 values.")
            return (matrix[3], matrix[0], matrix[1], matrix[7], matrix[4], matrix[5])
        scale = values(33550, ())
        tiepoints = values(33922, ())
        if len(scale) < 2 or len(tiepoints) < 6 or len(tiepoints) % 6:
            raise TiffFormatError("GeoTIFF pixel scale and tiepoint georeferencing are required.")
        i, j, _k, x, y, _z = tiepoints[:6]
        sx, sy = scale[:2]
        return (x - i * sx, sx, 0.0, y + j * sy, 0.0, -sy)

    @staticmethod
    def _nodata(value: str, samples: int):
        try:
            parsed = float(value)
        except ValueError as error:
            raise TiffFormatError("GDAL_NODATA contains a non-numeric value.") from error
        return (parsed,) * samples
