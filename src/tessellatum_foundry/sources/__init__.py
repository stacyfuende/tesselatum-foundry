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
from .protocols import FeatureReader, SourceAdapter
from .readers import (
    FeatureReaderError,
    GeoJsonFeatureCollectionReader,
    NdjsonFeatureReader,
)
from .stream import ExternalFeatureStreamError, iter_external_feature_batches
from .stac import StacResolutionError, parse_stac_item, resolve_stac_asset

__all__ = [
    "ExternalDataReference",
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
    "SourceDescriptor",
    "SourceIntegrityError",
    "SourceLimitExceeded",
    "StacResolutionError",
    "parse_stac_item",
    "resolve_stac_asset",
    "iter_feature_batches",
    "iter_external_feature_batches",
]
