import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.product_blueprints import plan_product_blueprint
from tessellatum_foundry.execution.product_execution import (
    ProductExecutionPreconditionError,
    compile_product_blueprint_recipe,
    execute_product_blueprint_plan,
)


VECTOR_MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"


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

    assert compiled["recipe"]["recipe_id"].startswith("product-buffer-product-")
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


def test_blueprint_execution_handoff_acceptance_and_manifest_assembly():
    from tessellatum_foundry.execution.product_acceptance import (
        assemble_product_manifest,
        evaluate_product_acceptance,
    )
    from tessellatum_foundry.execution.recipes import RecipeExecutionResult

    registry = CapabilityRegistry()
    blueprint = simple_blueprint()
    blueprint["acceptance"]["checks"] = [
        {
            "id": "runs",
            "kind": "computation",
            "description": "Runs succeeded",
            "validator": "runs.succeeded",
        },
        {
            "id": "outputs",
            "kind": "product",
            "description": "Output is present",
            "validator": "outputs.present",
        },
        {
            "id": "metadata",
            "kind": "product",
            "description": "Artifact metadata",
            "validator": "artifacts.metadata_valid",
        },
        {
            "id": "checksum",
            "kind": "product",
            "description": "Artifact integrity",
            "validator": "artifacts.checksum_verified",
        },
    ]
    plan = plan_product_blueprint(blueprint, capabilities=registry)

    class MemoryDefinitions:
        def __init__(self):
            self.cells = {}
            self.recipes = {}

        def put_cell(self, cell, *, created_by):
            self.cells[cell["cell_id"]] = cell

        def put_recipe(self, recipe, *, created_by):
            self.recipes[recipe["recipe_id"]] = recipe

    class ArtifactStore:
        def verify_artifact(self, record):
            assert record["checksum"]["algorithm"] == "sha256"

    class SuccessfulNode:
        def __init__(self):
            self.run = {
                "run_id": "run-buffer-001",
                "status": "succeeded",
                "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
                "outputs": [{"port_id": "result", "artifact_id": "buffer-artifact"}],
                "provenance": {"implementation": "test-double"},
            }

    class RegisteredRunService:
        def __init__(self):
            self.definitions = MemoryDefinitions()

        def execute_registered(self, *, recipe_id, version, actor_id):
            recipe = self.definitions.recipes[recipe_id]
            output = {
                "artifact_id": "buffer-artifact",
                "version": "1.0.0",
                "checksum": {"algorithm": "sha256", "value": "a" * 64},
                "media_type": "application/vnd.tessellatum.spatial-feature-collection+json",
                "size_bytes": 128,
                "spatial": {
                    "kind": "vector",
                    "crs": {"authority": "EPSG", "code": 32737},
                    "geometry_types": ["Polygon"],
                },
                "rights": {"license": "input-derived"},
                "storage": {"uri": "file:///test-artifacts/buffer.bin"},
            }
            return RecipeExecutionResult(
                execution_id="execution-buffer-001",
                recipe=recipe,
                status="succeeded",
                node_results={"buffer": SuccessfulNode()},
                outputs={"access-layer": output},
            )

    service = RegisteredRunService()
    execution = execute_product_blueprint_plan(
        blueprint,
        plan,
        capabilities=registry,
        recipe_service=service,
        actor_id="test-actor",
        **execution_inputs(),
    )
    acceptance = evaluate_product_acceptance(
        blueprint,
        execution,
        artifact_store=ArtifactStore(),
    )
    manifest = assemble_product_manifest(
        blueprint,
        plan,
        {"compilation_fingerprint": service.definitions.recipes[
            execution.recipe["recipe_id"]
        ]["metadata"]["compilation_fingerprint"]},
        execution,
        acceptance,
    )

    assert execution.status == "succeeded"
    assert acceptance["status"] == "accepted"
    assert acceptance["release_allowed"] is True
    assert manifest["outputs"][0]["status"] == "assembled"
    assert manifest["outputs"][0]["artifact"]["artifact_id"] == "buffer-artifact"
    assert manifest["provenance"]["runs"]["buffer"]["run_id"] == "run-buffer-001"
    assert manifest["manifest_fingerprint"]



@pytest.mark.skipif(
    not __import__("os").getenv("FOUNDRY_VECTOR_BUFFER_IMAGE"),
    reason="The real product-factory worker is built and configured only in container CI.",
)
def test_real_product_blueprint_runs_to_verified_geojson_bundle(tmp_path):
    import io
    import json
    import zipfile

    from tessellatum_foundry.execution.docker_worker import DockerWorker
    from tessellatum_foundry.execution.product_acceptance import (
        assemble_product_manifest,
        evaluate_product_acceptance,
    )
    from tessellatum_foundry.execution.product_delivery import build_geojson_product_bundle
    from tessellatum_foundry.execution.recipes import RecipeExecutionService
    from tessellatum_foundry.execution.runs import RunRepository
    from tessellatum_foundry.execution.service import VectorBufferRunService
    from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
    from tessellatum_foundry.storage.definitions import VersionedDefinitionStore

    media_type = "application/vnd.tessellatum.spatial-feature-collection+json"
    projected_crs = {"authority": "EPSG", "code": 32737}
    artifact_store = FileSystemArtifactStore(tmp_path / "artifacts")
    source = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "road-segment-001",
            "geometry": {
                "type": "LineString",
                "coordinates": [[320000, 9820000], [321000, 9820000]],
            },
            "properties": {"road_class": "primary"},
        }],
    }
    input_artifact = artifact_store.put_bytes(
        artifact_id="roads-source",
        version="1.0.0",
        content=json.dumps(source, allow_nan=False).encode("utf-8"),
        created_by="product-factory-integration",
        media_type=media_type,
        format_name="Foundry Spatial Feature Collection JSON",
        spatial={
            "kind": "vector",
            "crs": projected_crs,
            "geometry_types": ["LineString"],
        },
    )
    assert input_artifact["artifact_id"] == "roads-source"

    blueprint = simple_blueprint()
    blueprint["acceptance"]["checks"] = [
        {
            "id": "runs",
            "kind": "computation",
            "description": "Every registered Run succeeds.",
            "validator": "runs.succeeded",
            "required": True,
        },
        {
            "id": "outputs",
            "kind": "product",
            "description": "The declared output exists.",
            "validator": "outputs.present",
            "required": True,
        },
        {
            "id": "metadata",
            "kind": "product",
            "description": "Output Artifact metadata is complete.",
            "validator": "artifacts.metadata_valid",
            "required": True,
        },
        {
            "id": "checksum",
            "kind": "product",
            "description": "Output bytes match the registered checksum.",
            "validator": "artifacts.checksum_verified",
            "required": True,
        },
    ]
    registry = CapabilityRegistry()
    plan = plan_product_blueprint(blueprint, capabilities=registry)
    assert plan["status"] == "planned", plan, plan

    inputs = execution_inputs()
    compiled = compile_product_blueprint_recipe(
        plan, capabilities=registry, **inputs
    )
    runner = VectorBufferRunService(
        artifact_store=artifact_store,
        run_repository=RunRepository(tmp_path / "runs"),
        worker=DockerWorker(timeout_seconds=90),
    )
    recipe_service = RecipeExecutionService(
        cell_runner=runner,
        artifact_store=artifact_store,
        definitions=VersionedDefinitionStore(tmp_path / "definitions"),
    )
    execution = execute_product_blueprint_plan(
        blueprint,
        plan,
        capabilities=registry,
        recipe_service=recipe_service,
        actor_id="product-factory-integration",
        **inputs,
    )
    assert execution.status == "succeeded", execution.error
    assert len(execution.node_results) == 1
    run = next(iter(execution.node_results.values())).run
    assert run["status"] == "succeeded"
    assert run["worker"]["worker_type"] == "local_docker"

    acceptance = evaluate_product_acceptance(
        blueprint, execution, artifact_store=artifact_store
    )
    assert acceptance["status"] == "accepted", acceptance
    assert acceptance["release_allowed"] is True
    manifest = assemble_product_manifest(
        blueprint, plan, compiled, execution, acceptance
    )
    bundle = build_geojson_product_bundle(
        manifest, artifact_store=artifact_store
    )

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {
            "product-manifest.json",
            "manifest-fingerprint-input.json",
            "export-index.json",
            "outputs/access-layer.geojson",
        }
        output = json.loads(archive.read("outputs/access-layer.geojson"))
        assert output["type"] == "FeatureCollection"
        assert len(output["features"]) == 1
        assert output["features"][0]["geometry"]["type"] == "Polygon"
        exported_manifest = json.loads(archive.read("product-manifest.json"))
        assert exported_manifest["status"] == "accepted"
