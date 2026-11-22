"""External spatial data references and bounded source adapters."""

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
    "LocalFileSourceAdapter",
    "SourceAdapter",
    "SourceDescriptor",
    "SourceIntegrityError",
    "SourceLimitExceeded",
]
