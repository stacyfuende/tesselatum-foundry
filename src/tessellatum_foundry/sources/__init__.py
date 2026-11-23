"""External spatial data references and bounded source adapters."""

from .batches import (
    FeatureBatch,
    FeatureBatchError,
    FeatureExceedsBatchLimit,
    iter_feature_batches,
)
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

__all__ = [
    "ExternalDataReference",
    "FeatureBatch",
    "FeatureBatchError",
    "FeatureExceedsBatchLimit",
    "FeatureReader",
    "FeatureReaderError",
    "ExternalFeatureStreamError",
    "GeoJsonFeatureCollectionReader",
    "LocalFileSourceAdapter",
    "NdjsonFeatureReader",
    "SourceAdapter",
    "SourceDescriptor",
    "SourceIntegrityError",
    "SourceLimitExceeded",
    "iter_feature_batches",
    "iter_external_feature_batches",
]
