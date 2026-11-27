from tessellatum_foundry.execution.capabilities import CapabilityRegistry


def test_registered_capabilities_declare_operational_autonomy_profiles():
    registry = CapabilityRegistry()
    buffer = registry.get("vector.buffer", "1.0.0")
    reproject = registry.get("vector.reproject", "1.0.0")
    raster = registry.get("raster.window", "1.0.0")

    assert buffer["autonomy"]["side_effect"] == "workspace_write"
    assert reproject["autonomy"]["reversibility"] == "reversible"
    assert raster["autonomy"]["external_access"] is True
    assert raster["autonomy"]["approval_required"] is False
