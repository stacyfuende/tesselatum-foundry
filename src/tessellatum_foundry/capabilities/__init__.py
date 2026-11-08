"""Capability APIs with engine implementations imported on demand."""

from .buffer_contract import BufferContractError, BufferOutput
from .postgis_vector_buffer import buffer_feature_collection_postgis


def __getattr__(name: str):
    if name == "buffer_feature_collection":
        from .vector_buffer import buffer_feature_collection

        return buffer_feature_collection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BufferContractError",
    "BufferOutput",
    "buffer_feature_collection",
    "buffer_feature_collection_postgis",
]
