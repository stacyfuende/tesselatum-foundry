"""Tests for deterministic product acceptance and manifest assembly."""

from tessellatum_foundry.execution.product_acceptance import (
    assemble_product_manifest,
    evaluate_product_acceptance,
)


class FakeNodeRun:
    def __init__(self, status="succeeded"):
        self.run = {"status": status}


class FakeResult:
    def __init__(
        self,
        status="succeeded",
        outputs=None,
        node_results=None,
        recipe=None,
        execution_id="exec-1",
    ):
        self.status = status
        self.outputs = outputs or {}
        self.node_results = node_results or {"node": FakeNodeRun(status)}
        self.recipe = recipe or {
            "recipe_id": "r",
            "version": "1.0.0",
            "declared_outputs": [{"name": "out"}],
        }
        self.execution_id = execution_id


def artifact():
    return {
        "artifact_id": "out-artifact",
        "version": "1.0.0",
        "checksum": {"algorithm": "sha256", "value": "a" * 64},
        "media_type": "application/json",
        "size_bytes": 1,
        "storage": {"uri": "file:///objects/a"},
        "spatial": {"kind": "vector", "crs": {"authority": "EPSG", "code": 4326}, "geometry_types": ["Point"]},
    }


def blueprint(checks=None):
    return {
        "blueprint_id": "demo-product",
        "version": "1.0.0",
        "outputs": [{"id": "out", "product_type": "dataset", "experience": "Demo"}],
        "acceptance": {"checks": checks or [
            {"id": "run", "kind": "computation", "description": "Runs succeed", "required": True, "validator": "runs.succeeded"},
            {"id": "present", "kind": "product", "description": "Output present", "required": True, "validator": "outputs.present"},
            {"id": "metadata", "kind": "product", "description": "Metadata", "required": True, "validator": "artifacts.metadata_valid"},
        ]},
    }


def test_required_registered_checks_pass_accept_product():
    result = evaluate_product_acceptance(
        blueprint(), FakeResult(outputs={"out": artifact()})
    )
    assert result["status"] == "accepted"
    assert result["release_allowed"] is True
    assert all(check["status"] == "passed" for check in result["checks"])


def test_unknown_required_validator_blocks_release_as_review():
    b = blueprint([{
        "id": "valid-geometries",
        "kind": "product",
        "description": "Geometry validity",
        "validator": "geometry.valid",
    }])
    result = evaluate_product_acceptance(
        b, FakeResult(outputs={"out": artifact()})
    )
    assert result["status"] == "review_required"
    assert result["release_allowed"] is False
    assert result["checks"][0]["status"] == "unassessed"


def test_required_failed_check_rejects():
    result = evaluate_product_acceptance(
        blueprint(), FakeResult(status="failed", outputs={"out": artifact()})
    )
    assert result["status"] == "rejected"
    assert not result["release_allowed"]


def test_optional_failed_check_does_not_block_acceptance_but_warns():
    b = blueprint([{
        "id": "integrity",
        "kind": "product",
        "description": "Verify checksum",
        "required": False,
        "validator": "artifacts.checksum_verified",
    }])
    result = evaluate_product_acceptance(b, FakeResult(outputs={"out": artifact()}))
    assert result["status"] == "accepted"
    assert result["warnings"]


def test_manifest_provenance_and_fingerprint_stable():
    b = blueprint()
    plan = {"plan_fingerprint": "b" * 64}
    compiled = {"compilation_fingerprint": "c" * 64}
    execution = FakeResult(outputs={"out": artifact()})
    acceptance = evaluate_product_acceptance(b, execution)
    first = assemble_product_manifest(b, plan, compiled, execution, acceptance)
    second = assemble_product_manifest(b, plan, compiled, execution, acceptance)
    assert first["manifest_fingerprint"] == second["manifest_fingerprint"]
    assert first["outputs"][0]["status"] == "assembled"
    assert first["provenance"]["execution_id"] == "exec-1"


def test_missing_product_output_is_not_marked_assembled():
    b = blueprint()
    execution = FakeResult(outputs={})
    acceptance = evaluate_product_acceptance(b, execution)
    manifest = assemble_product_manifest(
        b, {"plan_fingerprint": "x"}, {}, execution, acceptance
    )
    assert manifest["outputs"][0]["status"] == "missing"
    assert manifest["release_allowed"] is False



def test_missing_declared_output_rejects_even_without_output_validator():
    b = blueprint([{
        "id": "some-check",
        "kind": "computation",
        "description": "An unrelated check",
        "validator": "runs.succeeded",
    }])
    result = evaluate_product_acceptance(b, FakeResult(outputs={}))
    assert result["status"] == "rejected"
    assert result["missing_outputs"] == ["out"]
    assert result["release_allowed"] is False
