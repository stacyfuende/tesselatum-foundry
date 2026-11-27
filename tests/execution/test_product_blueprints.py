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
    assert first["status"] == "planned"
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
