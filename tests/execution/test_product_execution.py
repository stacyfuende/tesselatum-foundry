import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.product_blueprints import plan_product_blueprint
from tessellatum_foundry.execution.product_execution import (
    ProductExecutionPreconditionError,
    compile_product_blueprint_recipe,
    execute_product_blueprint_plan,
)


def simple_blueprint():
    return {
        "blueprint_id": "buffer-product",
        "version": "1.0.0",
        "title": "Road access buffer",
        "intent": {"outcome": "Create a 500 metre buffer", "audience": "Planning team"},
        "evidence": {"requirements": []},
        "reasoning": {
            "nodes": [{
                "id": "buffer",
                "capability": "vector.buffer",
                "capability_version": "1.0.0",
                "inputs": {"features": "input:roads"},
                "parameters": {"distance": 500, "unit": "metre"},
            }],
        },
        "outputs": [{
            "id": "access-layer",
            "product_type": "dataset",
            "experience": "Validated access buffer layer",
        }],
        "acceptance": {"checks": [{
            "id": "valid-output",
            "kind": "computation",
            "description": "Output geometries are valid",
        }]},
    }


def execution_inputs():
    return {
        "cell_templates": {
            "buffer": {
                "capability": {
                    "capability_id": "vector.buffer",
                    "version": "1.0.0",
                },
                "constraints": {
                    "measurement_crs": {"authority": "EPSG", "code": 32737},
                    "linear_unit": "metre",
                },
                "output_contracts": {
                    "result": {
                        "data_kind": "vector",
                        "media_types": [
                            "application/vnd.tessellatum.spatial-feature-collection+json"
                        ],
                        "crs": {"authority": "EPSG", "code": 32737},
                        "geometry_types": ["Polygon", "MultiPolygon"],
                    },
                },
            },
        },
        "resolved_input_bindings": {
            "buffer.features": {
                "source": "artifact",
                "artifact": {
                    "artifact_id": "roads-source",
                    "version": "1.0.0",
                },
            },
        },
        "output_bindings": {
            "access-layer": {
                "node_id": "buffer",
                "output_port": "result",
            },
        },
    }


def test_blueprint_compiles_to_existing_recipe_contract_and_cell_runs():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    compiled = compile_product_blueprint_recipe(
        plan,
        capabilities=registry,
        **execution_inputs(),
    )

    assert compiled["recipe"]["recipe_id"] == "product-buffer-product"
    assert compiled["recipe"]["declared_outputs"] == [{
        "name": "access-layer",
        "node_id": "buffer",
        "output_port": "result",
    }]
    cell = next(iter(compiled["cells"].values()))
    assert cell["capability"] == {"capability_id": "vector.buffer", "version": "1.0.0"}
    assert cell["inputs"]["features"]["artifact"]["artifact_id"] == "roads-source"
    assert cell["parameters"]["distance"] == 500


def test_guided_decision_blocks_before_recipe_service_is_called():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    policy = {
        "policy_id": "guided-only",
        "version": "1.0.0",
        "default_mode": "guided",
        "rules": [],
    }
    plan = plan_product_blueprint(blueprint, capabilities=registry, policy=policy)

    class MustNotExecute:
        def execute(self, **kwargs):
            raise AssertionError("Run service must not be called for a guided plan.")

    with pytest.raises(ProductExecutionPreconditionError, match="Guided or explicit"):
        execute_product_blueprint_plan(
            blueprint,
            plan,
            capabilities=registry,
            recipe_service=MustNotExecute(),
            policy=policy,
            actor_id="test-actor",
            **execution_inputs(),
        )


def test_stale_plan_is_rejected_before_recipe_service_is_called():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    changed = simple_blueprint()
    changed["reasoning"]["nodes"][0]["parameters"]["distance"] = 750

    class MustNotExecute:
        def execute(self, **kwargs):
            raise AssertionError("Run service must not be called for a stale plan.")

    with pytest.raises(ProductExecutionPreconditionError, match="stale"):
        execute_product_blueprint_plan(
            changed,
            plan,
            capabilities=registry,
            recipe_service=MustNotExecute(),
            actor_id="test-actor",
            **execution_inputs(),
        )


def test_evidence_binding_must_preserve_declared_source_uri():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    blueprint["evidence"] = {
        "requirements": [],
        "provided_references": [{
            "id": "roads",
            "uri": "https://example.com/roads.geojson",
            "role": "road-network",
        }],
    }
    blueprint["reasoning"]["nodes"][0]["inputs"]["features"] = "evidence:roads"
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    inputs = execution_inputs()
    inputs["resolved_input_bindings"]["buffer.features"] = {
        "source": "external",
        "reference": {
            "uri": "https://other.example/roads.geojson",
            "media_type": "application/geo+json",
        },
        "spatial": {
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 4326},
            "geometry_types": ["LineString"],
        },
    }

    with pytest.raises(ProductExecutionPreconditionError, match="preserve the supplied reference URI"):
        compile_product_blueprint_recipe(
            plan,
            capabilities=registry,
            **inputs,
        )
