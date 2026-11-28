"""Process-local tenant runtime composition for the supported customer product.

Each tenant receives a separate LocalFoundry root and therefore separate
Artifact, Run and immutable-definition stores. This is a single-host
development/early-integration adapter, not distributed tenant provisioning.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

from tessellatum_foundry.local import LocalFoundry


_VECTOR_MEDIA_TYPE = (
    "application/vnd.tessellatum.spatial-feature-collection+json"
)
_PROJECTED_CRS = {"authority": "EPSG", "code": 32737}


def _site_standardization_templates() -> dict[str, dict[str, Any]]:
    """Return the reviewed Cell template for the installed site job."""
    return {
        "standardize": {
            "capability": {
                "capability_id": "vector.reproject",
                "version": "1.0.0",
            },
            "output_contracts": {
                "result": {
                    "data_kind": "vector",
                    "media_types": [_VECTOR_MEDIA_TYPE],
                    "crs": dict(_PROJECTED_CRS),
                    "geometry_types": [
                        "Point",
                        "MultiPoint",
                        "LineString",
                        "MultiLineString",
                        "Polygon",
                        "MultiPolygon",
                        "GeometryCollection",
                    ],
                },
            },
        },
    }


def _site_standardization_outputs() -> dict[str, dict[str, str]]:
    return {
        "standardized-sites": {
            "node_id": "standardize",
            "output_port": "result",
        },
    }


class LocalTenantRuntimeResolver:
    """Resolve stable, filesystem-isolated runtimes for authenticated tenants.

    The tenant identifier is never used as a path component. A SHA-256-derived
    directory name prevents traversal and keeps tenant names out of the
    filesystem layout. Runtime instances are cached per process; a deployment
    with multiple hosts must provide shared, tenant-scoped persistent storage
    and a distributed provisioning/locking strategy instead.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._runtimes: dict[str, tuple[LocalFoundry, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def __call__(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("A trusted non-empty tenant ID is required.")
        tenant_key = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._runtimes.get(tenant_key)
            if cached is not None:
                return cached[1]

            foundry = LocalFoundry(self.root / tenant_key)
            runtime = {
                "artifact_store": foundry.artifacts,
                "capabilities": foundry.capabilities,
                "recipe_service": foundry.recipes,
                "cell_templates": _site_standardization_templates(),
                "output_bindings": _site_standardization_outputs(),
                "contracts": foundry.contracts,
            }
            self._runtimes[tenant_key] = (foundry, runtime)
            return runtime
