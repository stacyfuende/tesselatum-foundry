from __future__ import annotations

import json
from pathlib import Path

import pytest

from tessellatum_foundry.execution.implementations import (
    ImplementationRegistry,
    ImplementationRegistryError,
)
from tessellatum_foundry.validation.contracts import ContractRegistry

ROOT = Path(__file__).resolve().parents[2]


def test_registry_loads_and_resolves_exact_conformant_manifest():
    registry = ImplementationRegistry()

    manifest = registry.require_conformant(
        implementation_id="vector-buffer-shapely",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )

    assert manifest["conformance"]["status"] == "passed"


def test_registry_rejects_manifest_for_different_capability_version():
    registry = ImplementationRegistry()

    with pytest.raises(ImplementationRegistryError, match="exact Capability version"):
        registry.require_conformant(
            implementation_id="vector-buffer-shapely",
            version="1.0.0",
            capability_id="vector.buffer",
            capability_version="2.0.0",
        )


def test_registry_fails_closed_when_manifest_has_not_passed_conformance(tmp_path):
    source = ROOT / "implementations" / "vector.buffer" / "shapely" / "1.0.0.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["conformance"]["status"] = "not_run"
    path = tmp_path / "vector.buffer" / "shapely" / "1.0.0.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = ImplementationRegistry(tmp_path, ContractRegistry())

    with pytest.raises(ImplementationRegistryError, match="has not passed conformance"):
        registry.require_conformant(
            implementation_id="vector-buffer-shapely",
            version="1.0.0",
            capability_id="vector.buffer",
            capability_version="1.0.0",
        )


def test_manifest_checksum_is_stable_and_detached_from_returned_objects():
    registry = ImplementationRegistry()
    first = registry.manifest_checksum("vector-buffer-shapely", "1.0.0")
    manifest = registry.get("vector-buffer-shapely", "1.0.0")
    manifest["engine"] = "modified by caller"
    second = registry.manifest_checksum("vector-buffer-shapely", "1.0.0")

    assert len(first) == 64
    assert first == second
