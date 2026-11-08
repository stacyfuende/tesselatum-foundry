from __future__ import annotations

import pytest

from tessellatum_foundry.execution.capabilities import (
    CapabilityRegistry,
    CapabilityRegistryError,
)


def test_registry_resolves_canonical_capability_version():
    registry = CapabilityRegistry()

    capability = registry.get("vector.buffer", "1.0.0")

    assert capability["capability_id"] == "vector.buffer"
    assert capability["version"] == "1.0.0"
    assert registry.require_exact(capability) == capability


def test_registry_rejects_same_version_with_modified_semantics():
    registry = CapabilityRegistry()
    candidate = registry.get("vector.buffer", "1.0.0")
    candidate["parameter_schema"]["properties"]["distance"]["maximum"] = 1000

    with pytest.raises(CapabilityRegistryError, match="differs from its canonical"):
        registry.require_exact(candidate)


def test_registry_rejects_unregistered_capability_version():
    registry = CapabilityRegistry()
    candidate = registry.get("vector.buffer", "1.0.0")
    candidate["version"] = "2.0.0"

    with pytest.raises(CapabilityRegistryError, match="is not registered"):
        registry.require_exact(candidate)
