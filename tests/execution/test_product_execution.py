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

    with pytest.raises(
        ProductExecutionPreconditionError,
        match="preserve the supplied reference URI",
    ):
        compile_product_blueprint_recipe(
            plan,
            capabilities=registry,
            **inputs,
        )



def test_blueprint_dependency_becomes_recipe_edge_and_cell_output_binding():
    registry = CapabilityRegistry()
    blueprint = {
        "blueprint_id": "reproject-and-buffer",
        "version": "1.0.0",
        "title": "Reproject and buffer",
        "intent": {"outcome": "Buffer projected roads", "audience": "Planner"},
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
            "product_type": "dataset",
            "experience": "Projected road buffers",
        }],
        "acceptance": {"checks": [{
            "id": "valid-output",
            "kind": "computation",
            "description": "Output geometries are valid",
        }]},
    }
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    project_output = {
        "data_kind": "vector",
        "media_types": ["application/vnd.tessellatum.spatial-feature-collection+json"],
        "crs": {"authority": "EPSG", "code": 32737},
        "geometry_types": [
            "Point", "MultiPoint", "LineString", "MultiLineString",
            "Polygon", "MultiPolygon", "GeometryCollection",
        ],
    }
    templates = execution_inputs()["cell_templates"]
    templates["project"] = {
        "capability": {"capability_id": "vector.reproject", "version": "1.0.0"},
        "output_contracts": {"result": project_output},
    }
    templates["buffer"]["constraints"] = {
        "measurement_crs": {"authority": "EPSG", "code": 32737},
        "linear_unit": "metre",
    }
    templates["buffer"]["output_contracts"] = {
        "result": {
            "data_kind": "vector",
            "media_types": ["application/vnd.tessellatum.spatial-feature-collection+json"],
            "crs": {"authority": "EPSG", "code": 32737},
            "geometry_types": ["Polygon", "MultiPolygon"],
        },
    }
    inputs = execution_inputs()
    inputs["cell_templates"] = templates
    inputs["resolved_input_bindings"] = {
        "project.features": {
            "source": "artifact",
            "artifact": {"artifact_id": "roads-source", "version": "1.0.0"},
        },
    }
    compiled = compile_product_blueprint_recipe(
        plan,
        capabilities=registry,
        **inputs,
    )

    assert compiled["recipe"]["edges"] == [{
        "from": {"node_id": "project", "output_port": "result"},
        "to": {"node_id": "buffer", "input_port": "features"},
    }]
    buffer_cell = next(
        cell for cell in compiled["cells"].values()
        if cell["capability"]["capability_id"] == "vector.buffer"
    )
    project_cell = next(
        cell for cell in compiled["cells"].values()
        if cell["capability"]["capability_id"] == "vector.reproject"
    )
    assert buffer_cell["inputs"]["features"] == {
        "source": "cell_output",
        "cell_id": project_cell["cell_id"],
        "cell_version": project_cell["version"],
        "output_port": "result",
    }


def test_automatic_plan_is_handed_to_existing_recipe_run_service():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    plan = plan_product_blueprint(blueprint, capabilities=registry)

    class MemoryDefinitions:
        def __init__(self):
            self.cells = {}
            self.recipes = {}

        def put_cell(self, cell, *, created_by):
            self.cells[cell["cell_id"]] = (cell, created_by)

        def put_recipe(self, recipe, *, created_by):
            self.recipes[recipe["recipe_id"]] = (recipe, created_by)

    class CaptureRecipeService:
        def __init__(self):
            self.called = False
            self.definitions = MemoryDefinitions()

        def execute_registered(self, *, recipe_id, version, actor_id):
            self.called = True
            self.arguments = {
                "recipe_id": recipe_id,
                "version": version,
                "actor_id": actor_id,
            }
            return "run-result"

    service = CaptureRecipeService()
    result = execute_product_blueprint_plan(
        blueprint,
        plan,
        capabilities=registry,
        recipe_service=service,
        actor_id="test-actor",
        **execution_inputs(),
    )

    assert result == "run-result"
    assert service.called
    assert service.arguments["actor_id"] == "test-actor"
    assert len(service.definitions.cells) == 1
    assert len(service.definitions.recipes) == 1
    saved_recipe = next(iter(service.definitions.recipes.values()))[0]
    assert (
        saved_recipe["metadata"]["product_plan_fingerprint"]
        == plan["plan_fingerprint"]
    )


def test_compilation_identity_changes_when_resolved_artifact_changes():
    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    inputs = execution_inputs()
    first = compile_product_blueprint_recipe(
        plan, capabilities=registry, **inputs
    )
    changed = execution_inputs()
    changed["resolved_input_bindings"]["buffer.features"]["artifact"]["version"] = (
        "2.0.0"
    )
    second = compile_product_blueprint_recipe(
        plan, capabilities=registry, **changed
    )

    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert first["compilation_fingerprint"] != second["compilation_fingerprint"]
    assert first["recipe"]["recipe_id"] != second["recipe"]["recipe_id"]
