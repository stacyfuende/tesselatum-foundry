"""External spatial data references and bounded source adapters."""

from .batches import (
    FeatureBatch,
    FeatureBatchError,
    FeatureExceedsBatchLimit,
    iter_feature_batches,
)
from .http import HttpSourceAdapter, SourceAccessError
from .local import LocalFileSourceAdapter
from .models import (
    ExternalDataReference,
    SourceDescriptor,
    SourceIntegrityError,
    SourceLimitExceeded,
)
from .protocols import FeatureReader, RangeSourceAdapter, SourceAdapter
from .raster import BudgetedRasterRangeReader, RasterContractError, RasterMetadata, RasterWindow
from .readers import (
    FeatureReaderError,
    GeoJsonFeatureCollectionReader,
    NdjsonFeatureReader,
)
from .stream import ExternalFeatureStreamError, iter_external_feature_batches
from .stac import StacResolutionError, parse_stac_item, resolve_stac_asset
from .stac_client import StacItemSourceResolver
from .stac_search import StacApiSearchClient, StacSearchError
from .stac_http import StacSearchTransportError, UrllibStacSearchTransport
from .cog_structure import TiffStructureAssessment, assess_cog_structure
from .tiff import TiffDirectory, TiffFormatError, TiffLayout, TiffRaster, TiffRangeReader\nfrom .tile_selection import RasterTileSelection, select_tiff_tiles

__all__ = [
    "ExternalDataReference",
    "BudgetedRasterRangeReader",
    "RasterContractError",
    "RasterMetadata",
    "RasterWindow",
    "TiffDirectory",
    "TiffStructureAssessment",
    "assess_cog_structure",
    "TiffFormatError",
    "TiffLayout",
    "TiffRaster",
    "TiffRangeReader",\n    "RasterTileSelection",\n    "select_tiff_tiles",
    "FeatureBatch",
    "FeatureBatchError",
    "FeatureExceedsBatchLimit",
    "FeatureReader",
    "FeatureReaderError",
    "ExternalFeatureStreamError",
    "GeoJsonFeatureCollectionReader",
    "HttpSourceAdapter",
    "LocalFileSourceAdapter",
    "NdjsonFeatureReader",
    "SourceAccessError",
    "SourceAdapter",
    "RangeSourceAdapter",
    "SourceDescriptor",
    "SourceIntegrityError",
    "SourceLimitExceeded",
    "StacResolutionError",
    "StacItemSourceResolver",
    "StacApiSearchClient",
    "StacSearchError",
    "StacSearchTransportError",
    "UrllibStacSearchTransport",
    "parse_stac_item",
    "resolve_stac_asset",
    "iter_feature_batches",
    "iter_external_feature_batches",
]
