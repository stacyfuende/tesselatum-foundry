"""Registry of versioned capability implementation manifests."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tessellatum_foundry.data import foundry_data_dir
from tessellatum_foundry.validation.contracts import ContractRegistry


class ImplementationRegistryError(ValueError):
    """Raised when an implementation is missing or not eligible for execution."""


class ImplementationRegistry:
    """Load schema-valid implementation manifests from the Foundry registry."""

    def __init__(
        self,
        implementation_dir: Path | None = None,
        contracts: ContractRegistry | None = None,
    ) -> None:
        self.implementation_dir = implementation_dir or foundry_data_dir(
            "implementations"
        )
        self.contracts = contracts or ContractRegistry()
        self._manifests: dict[tuple[str, str], dict[str, Any]] = {}
        for path in sorted(self.implementation_dir.rglob("*.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.contracts.validate("capability-implementation.schema.json", manifest)
            key = (manifest["implementation_id"], manifest["version"])
            if key in self._manifests:
                raise ImplementationRegistryError(
                    f"Duplicate implementation manifest: {key[0]}@{key[1]}."
                )
            self._manifests[key] = manifest

    def list(self) -> list[dict[str, Any]]:
        """Return implementation manifests in stable identifier/version order."""
        return [
            deepcopy(self._manifests[key])
            for key in sorted(self._manifests)
        ]

    def get(self, implementation_id: str, version: str) -> dict[str, Any]:
        """Return an exact implementation manifest or fail closed."""
        key = (implementation_id, version)
        try:
            return deepcopy(self._manifests[key])
        except KeyError as error:
            raise ImplementationRegistryError(
                f"Implementation {implementation_id}@{version} is not registered."
            ) from error

    def manifest_checksum(self, implementation_id: str, version: str) -> str:
        """Return the SHA-256 digest of the canonical registered manifest."""
        manifest = self.get(implementation_id, version)
        canonical = json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def require_conformant(
        self,
        *,
        implementation_id: str,
        version: str,
        capability_id: str,
        capability_version: str,
    ) -> dict[str, Any]:
        """Resolve an implementation only when its manifest matches and passed conformance."""
        manifest = self.get(implementation_id, version)
        if (
            manifest["capability_id"] != capability_id
            or manifest["capability_version"] != capability_version
        ):
            raise ImplementationRegistryError(
                "Implementation manifest does not target the exact Capability version."
            )
        if manifest["conformance"]["status"] != "passed":
            raise ImplementationRegistryError(
                f"Implementation {implementation_id}@{version} has not passed conformance."
            )
        return manifest
