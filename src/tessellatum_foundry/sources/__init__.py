"""External spatial data references and bounded source adapters."""

from .batches import FeatureBatch, FeatureBatchError, FeatureExceedsBatchLimit, iter_feature_batches
from .cog_structure import TiffStructureAssessment, assess_cog_structure
from .http import HttpSourceAdapter, SourceAccessError
from .local import LocalFileSourceAdapter
from .models import (
    ExternalDataReference,
    SourceDescriptor,
    SourceIntegrityError,
    SourceLimitExceeded,
)
from .nodata import (
    NoDataArithmeticResult,
    apply_nodata_aware_binary,
    build_validity_mask,
    sample_is_valid,
    window_validity_mask,
)
from .overview_selection import (
    SelectedTiffOverview,
    overview_factors_from_dimensions,
    overview_factors_from_tiff_directories,
    select_overview_factor,
    select_tiff_overview,
)
from .protocols import FeatureReader, RangeSourceAdapter, SourceAdapter
from .raster import BudgetedRasterRangeReader, RasterContractError, RasterMetadata, RasterWindow
from .readers import FeatureReaderError, GeoJsonFeatureCollectionReader, NdjsonFeatureReader
from .stac import StacResolutionError, parse_stac_item, resolve_stac_asset
from .stac_client import StacItemSourceResolver
from .stac_http import StacSearchTransportError, UrllibStacSearchTransport
from .stac_search import StacApiSearchClient, StacSearchError
from .stream import ExternalFeatureStreamError, iter_external_feature_batches
from .tile_decode import (
    DecodedRasterTile,
    decode_deflate_tiff_tile,
    decode_tiff_tile,
    decode_uncompressed_tiff_tile,
)
from .tile_reads import RetrievedRasterTile, read_selected_tiff_tiles
from .tile_selection import RasterTileSelection, select_tiff_tiles
from .tiff import TiffDirectory, TiffFormatError, TiffLayout, TiffRaster, TiffRangeReader
from .window_assembly import RasterWindowBuffer, assemble_tiff_window
from .window_read import TiffWindowRead, read_tiff_window

__all__ = [
    "ExternalDataReference", "BudgetedRasterRangeReader", "RasterContractError",
    "RasterMetadata", "RasterWindow", "TiffDirectory", "TiffStructureAssessment",
    "assess_cog_structure", "TiffFormatError", "TiffLayout", "TiffRaster",
    "TiffRangeReader", "RasterTileSelection", "select_tiff_tiles",
    "RetrievedRasterTile", "read_selected_tiff_tiles", "DecodedRasterTile",
    "decode_uncompressed_tiff_tile", "decode_deflate_tiff_tile", "decode_tiff_tile",
    "RasterWindowBuffer", "assemble_tiff_window", "TiffWindowRead", "read_tiff_window",
    "sample_is_valid", "build_validity_mask", "NoDataArithmeticResult",
    "apply_nodata_aware_binary", "window_validity_mask", "select_overview_factor",
    "overview_factors_from_dimensions", "overview_factors_from_tiff_directories",
    "SelectedTiffOverview", "select_tiff_overview", "FeatureBatch",
    "FeatureBatchError", "FeatureExceedsBatchLimit", "FeatureReader",
    "FeatureReaderError", "ExternalFeatureStreamError", "GeoJsonFeatureCollectionReader",
    "HttpSourceAdapter", "LocalFileSourceAdapter", "NdjsonFeatureReader",
    "SourceAccessError", "SourceAdapter", "RangeSourceAdapter", "SourceDescriptor",
    "SourceIntegrityError", "SourceLimitExceeded", "StacResolutionError",
    "StacItemSourceResolver", "StacApiSearchClient", "StacSearchError",
    "StacSearchTransportError", "UrllibStacSearchTransport", "parse_stac_item",
    "resolve_stac_asset", "iter_feature_batches", "iter_external_feature_batches",
]
