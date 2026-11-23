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
from .protocols import SourceAdapter

__all__ = [
    "ExternalDataReference",
    "FeatureBatch",
    "FeatureBatchError",
    "FeatureExceedsBatchLimit",
    "LocalFileSourceAdapter",
    "SourceAdapter",
    "SourceDescriptor",
    "SourceIntegrityError",
    "SourceLimitExceeded",
    "iter_feature_batches",
]
