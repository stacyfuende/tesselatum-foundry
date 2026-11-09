"""Registry of immutable, schema-valid Capability contract versions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tessellatum_foundry.data import foundry_data_dir
from tessellatum_foundry.validation.contracts import ContractRegistry


class CapabilityRegistryError(ValueError):
    """Raised when a Capability is missing or differs from its canonical contract."""


class CapabilityRegistry:
    """Resolve exact Capability versions from the canonical repository registry."""

    def __init__(
        self,
        capability_dir: Path | None = None,
        contracts: ContractRegistry | None = None,
    ) -> None:
        self.capability_dir = capability_dir or foundry_data_dir("capabilities")
        self.contracts = contracts or ContractRegistry()
        self._capabilities: dict[tuple[str, str], dict[str, Any]] = {}
        for path in sorted(self.capability_dir.rglob("*.json")):
            capability = json.loads(path.read_text(encoding="utf-8"))
            self.contracts.validate("capability.schema.json", capability)
            key = (capability["capability_id"], capability["version"])
            if key in self._capabilities:
                raise CapabilityRegistryError(
                    f"Duplicate Capability contract: {key[0]}@{key[1]}."
                )
            self._capabilities[key] = capability

    def list(self) -> list[dict[str, Any]]:
        """Return registered Capability contracts in stable identifier/version order."""
        return [
            deepcopy(self._capabilities[key])
            for key in sorted(self._capabilities)
        ]

    def get(self, capability_id: str, version: str) -> dict[str, Any]:
        """Return a copy of the exact canonical Capability contract."""
        key = (capability_id, version)
        try:
            return deepcopy(self._capabilities[key])
        except KeyError as error:
            raise CapabilityRegistryError(
                f"Capability {capability_id}@{version} is not registered."
            ) from error

    def require_exact(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Fail closed unless the supplied object exactly matches its registered version."""
        capability = self.get(candidate["capability_id"], candidate["version"])
        try:
            candidate_json = json.dumps(
                candidate, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            canonical_json = json.dumps(
                capability, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise CapabilityRegistryError(
                "Supplied Capability contract is not canonical JSON data."
            ) from error
        if candidate_json != canonical_json:
            raise CapabilityRegistryError(
                "Supplied Capability contract differs from its canonical registered version."
            )
        return capability
