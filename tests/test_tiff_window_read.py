from __future__ import annotations

from tessellatum_foundry.sources import (
    RasterMetadata,
    RasterWindow,
    TiffDirectory,
    TiffLayout,
    TiffRaster,
    read_tiff_window,
)


class MemoryRangeSource:
    def __init__(self, offset: int, payload: bytes):
        self.offset = offset
        self.payload = payload
        self.reads = []

    def read(self, *, offset: int, length: int) -> bytes:
        self.reads.append((offset, length))
        assert offset == self.offset
        assert length == len(self.payload)
        return self.payload


class IndexedTiffReader:
    def __init__(self, directories, raster, source):
        self.directories = directories
        self.raster = raster
        self.source = source

    def read_directory_index(self, *, file_size: int, max_directories: int):
        assert file_size == self.raster.layout.file_size
        return self.directories

    def read(self, *, file_size: int):
        assert file_size == self.raster.layout.file_size
        return self.raster


def directory(width, height, *, reduced, offset, byte_count):
    across = (width + 15) // 16
    down = (height + 15) // 16
    return TiffDirectory(
        offset=offset,
        width=width,
        height=height,
        tiled=True,
        block_offsets=tuple(offset + index for index in range(across * down)),
        block_byte_counts=tuple(byte_count for _ in range(across * down)),
        subifd_offsets=(),
        next_ifd_offset=0,
        tile_width=16,
        tile_height=16,
        samples_per_pixel=1,
        planar_configuration=1,
        compression=1,
        new_subfile_type=1 if reduced else 0,
    )


def test_reads_selected_overview_through_budgeted_tile_decode_and_assembly():
    payload = bytes(range(256))
    source = MemoryRangeSource(512, payload)
    base_metadata = RasterMetadata(
        width=32,
        height=32,
        band_count=1,
        dtypes=("uint8",),
        transform=(0, 1, 0, 32, 0, -1),
    )
    base = directory(32, 32, reduced=False, offset=100, byte_count=256)
    overview = directory(16, 16, reduced=True, offset=512, byte_count=256)
    raster = TiffRaster(
        layout=TiffLayout("little", False, 8, 1024),
        metadata=base_metadata,
        compression=1,
        tiled=True,
        tile_offsets=base.block_offsets,
        tile_byte_counts=base.block_byte_counts,
        strip_offsets=(),
        strip_byte_counts=(),
    )
    reader = IndexedTiffReader((base, overview), raster, source)

    result = read_tiff_window(
        reader,
        file_size=1024,
        window=RasterWindow(row_offset=0, column_offset=0, height=16, width=16),
        target_downsample=2,
    )

    assert result.overview.factor == 2
    assert result.overview.directory is overview
    assert result.buffer.samples == payload
    assert (result.buffer.window.width, result.buffer.window.height) == (16, 16)
    assert source.reads == [(512, 256)]
