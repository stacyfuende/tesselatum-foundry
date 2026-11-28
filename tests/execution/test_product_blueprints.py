from copy import deepcopy

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.product_blueprints import plan_product_blueprint


def blueprint():
    return {
        "blueprint_id": "buffered-access-study",
        "version": "1.0.0",
        "title": "Buffered access study",
        "intent": {"outcome": "Create a proximity analysis layer", "audience": "Planning team"},
        "evidence": {"requirements": []},
        "reasoning": {
            "nodes": [
                {
                    "id": "project",
                    "capability": "vector.reproject",
                    "capability_version": "1.0.0",
                    "inputs": {"features": "input:roads"},
                    "parameters": {"target_crs": {"authority": "EPSG", "code": 32737}},
                },
                {
                    "id": "buffer",
                    "capability": "vector.buffer",
                    "capability_version": "1.0.0",
                    "inputs": {"features": "project.result"},
                    "parameters": {"distance": 500, "unit": "metre"},
                },
            ],
        },
        "outputs": [{
            "id": "access-layer",
            "product_type": "map",
            "experience": "An interactive map of 500 metre access buffers",
        }],
        "acceptance": {"checks": [{
            "id": "valid-output",
            "kind": "computation",
            "description": "Output geometries are valid",
        }]},
    }


def test_blueprint_compiles_to_deterministic_topological_plan():
    first = plan_product_blueprint(blueprint(), capabilities=CapabilityRegistry())
    second = plan_product_blueprint(blueprint(), capabilities=CapabilityRegistry())
    assert first["status"] == "planned", first
    assert first["executable"] is False
    assert first["node_order"] == ["project", "buffer"]
    assert first["node_order"] == second["node_order"]
    assert first["nodes"][1]["bindings"]["features"] == "project.result"
    assert all(item["mode"] == "automatic" for item in first["autonomy_decisions"])


def test_missing_capability_blocks_plan_without_inventing_method():
    item = blueprint()
    item["reasoning"]["nodes"][0]["capability"] = "vector.magic"
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "blocked"
    assert result["missing_capabilities"][0]["capability_id"] == "vector.magic"
    assert not any(node["capability_id"] == "vector.magic" for node in result["nodes"])


def test_unknown_output_port_is_reported():
    item = blueprint()
    item["reasoning"]["nodes"][1]["inputs"]["features"] = "project.not_a_port"
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "blocked"
    assert any(f["code"] == "unknown_output_port" for f in result["findings"])


def test_cycles_are_blocked():
    item = blueprint()
    item["reasoning"]["nodes"][0]["depends_on"] = ["buffer"]
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "blocked"
    assert any(f["code"] == "dependency_cycle" for f in result["findings"])


def test_missing_required_evidence_is_reported():
    item = blueprint()
    item["evidence"]["requirements"] = [{
        "id": "roads-source", "role": "road-network", "required": True,
    }]
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "blocked"
    assert result["missing_evidence"][0]["id"] == "roads-source"


def test_planner_does_not_mutate_blueprint():
    item = blueprint()
    original = deepcopy(item)
    plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert item == original

def test_dependency_resolution_is_independent_of_blueprint_declaration_order():
    item = blueprint()
    item["reasoning"]["nodes"].reverse()
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "planned", result
    assert result["node_order"] == ["project", "buffer"]



def test_plan_fingerprint_is_stable_and_tracks_policy_changes():
    item = blueprint()
    first = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    second = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    policy = {
        "policy_id": "stricter",
        "version": "1.0.0",
        "default_mode": "guided",
        "rules": [],
    }
    third = plan_product_blueprint(item, capabilities=CapabilityRegistry(), policy=policy)
    assert third["plan_fingerprint"] != first["plan_fingerprint"]


def test_external_delivery_requires_explicit_release_authorisation():
    item = blueprint()
    item["outputs"][0]["delivery_targets"] = ["https://customer.example/product"]
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "approval_required", result
    assert result["approval_required"] is True
    assert any(
        decision["node_id"] == "access-layer"
        and decision["mode"] == "explicit"
        for decision in result["autonomy_decisions"]
    )


def test_evidence_binding_requires_a_declared_reference_role():
    item = blueprint()
    item["evidence"]["provided_references"] = [{
        "id": "roads", "uri": "https://example.com/roads.geojson",
    }]
    item["reasoning"]["nodes"][0]["inputs"]["features"] = "evidence:roads"
    result = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    assert result["status"] == "blocked"
    assert any(f["code"] == "evidence_role_missing" for f in result["findings"])


def test_duplicate_evidence_reference_ids_are_rejected():
    import pytest
    from tessellatum_foundry.execution.product_blueprints import ProductBlueprintPlanError

    item = blueprint()
    item["evidence"]["provided_references"] = [
        {"id": "roads-a", "uri": "https://example.com/a", "role": "road-network"},
        {"id": "roads-a", "uri": "https://example.com/b", "role": "road-network"},
    ]
    with pytest.raises(ProductBlueprintPlanError, match="duplicate evidence reference"):
        plan_product_blueprint(item, capabilities=CapabilityRegistry())


def test_requested_autonomy_mode_is_part_of_plan_identity():
    item = blueprint()
    automatic = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    guided = plan_product_blueprint(
        item, capabilities=CapabilityRegistry(), requested_mode="guided"
    )
    assert guided["plan_fingerprint"] != automatic["plan_fingerprint"]
    assert all(
        decision["mode"] == "guided"
        for decision in guided["autonomy_decisions"]
    )
