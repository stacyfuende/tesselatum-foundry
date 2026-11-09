"""Tessellatum Foundry domain and validation primitives.

The local SDK is imported lazily so optional geometry engines remain optional
for consumers that only need contracts or a specific backend adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"
__all__ = [
    "FoundryAPIError",
    "FoundryClient",
    "FoundryTransportError",
    "LocalFoundry",
    "__version__",
]

if TYPE_CHECKING:
    from tessellatum_foundry.client import FoundryClient
    from tessellatum_foundry.local import LocalFoundry


def __getattr__(name: str) -> Any:
    if name == "LocalFoundry":
        from tessellatum_foundry.local import LocalFoundry

        return LocalFoundry
    if name in {"FoundryClient", "FoundryAPIError", "FoundryTransportError"}:
        from tessellatum_foundry import client

        return getattr(client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
