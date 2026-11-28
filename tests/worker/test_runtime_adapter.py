from __future__ import annotations

from types import SimpleNamespace

import pytest

from tessellatum_foundry.worker.runtime_adapter import adapt_local_foundry_runtime


def test_adapter_maps_existing_local_foundry_services_without_replacing_them():
    foundry = SimpleNamespace(artifacts=object(), capabilities=object(), recipes=object(), contracts=object())
    templates = {"buffer": {"capability_id": "vector.buffer"}}
    bindings = {"result": {"output": "artifact"}}
    runtime = adapt_local_foundry_runtime(foundry, cell_templates=templates, output_bindings=bindings)
    assert runtime["artifact_store"] is foundry.artifacts
    assert runtime["capabilities"] is foundry.capabilities
    assert runtime["recipe_service"] is foundry.recipes
    assert runtime["contracts"] is foundry.contracts
    assert runtime["cell_templates"] is templates
    assert runtime["output_bindings"] is bindings
    assert runtime["max_export_bytes"] == 100 * 1024 * 1024


@pytest.mark.parametrize("templates,bindings", [({}, {"x": {}}), ({"x": {}}, {})])
def test_adapter_requires_explicit_nonempty_installed_mappings(templates, bindings):
    foundry = SimpleNamespace(artifacts=object(), capabilities=object(), recipes=object(), contracts=object())
    with pytest.raises(ValueError):
        adapt_local_foundry_runtime(foundry, cell_templates=templates, output_bindings=bindings)


def test_adapter_rejects_incomplete_runtime_and_invalid_limit():
    with pytest.raises(ValueError, match="composition is incomplete"):
        adapt_local_foundry_runtime(SimpleNamespace(artifacts=object()), cell_templates={"x": {}}, output_bindings={"x": {}})
    foundry = SimpleNamespace(artifacts=object(), capabilities=object(), recipes=object(), contracts=object())
    with pytest.raises(ValueError, match="positive integer"):
        adapt_local_foundry_runtime(foundry, cell_templates={"x": {}}, output_bindings={"x": {}}, max_export_bytes=0)
