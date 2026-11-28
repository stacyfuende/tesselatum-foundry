"""Deterministic Product Blueprint acceptance and assembly, without release side effects."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from tessellatum_foundry.execution.recipes import RecipeExecutionResult


_SUPPORTED_VALIDATORS = {
    "runs.succeeded",
    "outputs.present",
    "artifacts.metadata_valid",
    "artifacts.checksum_verified",
}


def evaluate_product_acceptance(
    blueprint: dict[str, Any],
    execution: RecipeExecutionResult,
    *,
    artifact_store: Any | None = None,
) -> dict[str, Any]:
    """Evaluate only explicitly registered validator semantics; unknown checks remain unassessed."""
    results = []
    outputs = execution.outputs or {}
    for check in blueprint.get("acceptance", {}).get("checks", []):
        validator = check.get("validator")
        required = check.get("required", True)
        if validator not in _SUPPORTED_VALIDATORS:
            results.append({
                "check_id": check["id"],
                "validator": validator,
                "required": required,
                "status": "unassessed",
                "reason": "No registered validator semantics for this check.",
            })
            continue
        passed, reason = _evaluate_validator(
            validator, execution, outputs, artifact_store
        )
        results.append({
            "check_id": check["id"],
            "validator": validator,
            "required": required,
            "status": "passed" if passed else "failed",
            "reason": reason,
        })

    declared_output_ids = {item["id"] for item in blueprint.get("outputs", [])}
    missing_outputs = sorted(declared_output_ids - set(outputs))
    required_failed = any(item["required"] and item["status"] == "failed" for item in results)
    required_unassessed = any(
        item["required"] and item["status"] == "unassessed" for item in results
    )
    optional_failed = any(not item["required"] and item["status"] == "failed" for item in results)
    if execution.status != "succeeded" or required_failed or missing_outputs:
        status = "rejected"
    elif required_unassessed:
        status = "review_required"
    else:
        status = "accepted"
    return {
        "status": status,
        "checks": results,
        "summary": {
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "unassessed": sum(item["status"] == "unassessed" for item in results),
            "optional_failures": sum(
                not item["required"] and item["status"] == "failed" for item in results
            ),
            "execution_status": execution.status,
        },
        "release_allowed": status == "accepted",
        "missing_outputs": missing_outputs,
        "warnings": (
            ["Optional acceptance check failed."] if optional_failed else []
        ),
    }


def _evaluate_validator(
    validator: str,
    execution: RecipeExecutionResult,
    outputs: dict[str, dict[str, Any]],
    artifact_store: Any | None,
) -> tuple[bool, str]:
    if validator == "runs.succeeded":
        passed = (
            execution.status == "succeeded"
            and bool(execution.node_results)
            and all(
                result.run.get("status") == "succeeded"
                for result in execution.node_results.values()
            )
        )
        reason = (
            "Every Recipe node Run succeeded."
            if passed
            else "Recipe or one or more Runs did not succeed."
        )
        return passed, reason
    if validator == "outputs.present":
        expected = {item["name"] for item in execution.recipe.get("declared_outputs", [])}
        # Recipe result's output map uses the declared output names.
        passed = bool(expected) and expected.issubset(outputs)
        reason = (
            "All declared outputs are present."
            if passed
            else "One or more declared outputs are missing."
        )
        return passed, reason
    if validator == "artifacts.metadata_valid":
        passed = bool(outputs) and all(
            isinstance(item, dict)
            and item.get("artifact_id")
            and item.get("version")
            and item.get("checksum", {}).get("algorithm") == "sha256"
            and len(item.get("checksum", {}).get("value", "")) == 64
            and item.get("storage", {}).get("uri")
            for item in outputs.values()
        )
        reason = (
            "Output Artifact metadata contains required identity, checksum, and storage fields."
            if passed
            else "Artifact metadata is incomplete or invalid."
        )
        return passed, reason
    if validator == "artifacts.checksum_verified":
        if artifact_store is None or not outputs:
            return False, (
                "Artifact store is unavailable or no outputs exist for integrity verification."
            )
        try:
            for artifact in outputs.values():
                artifact_store.verify_artifact(artifact)
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            return False, f"Artifact integrity verification failed: {error}"
        return True, (
            "All output Artifact bytes match their recorded SHA-256 and size."
        )
    return False, "Validator not registered."


def assemble_product_manifest(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
    compiled: dict[str, Any],
    execution: RecipeExecutionResult,
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    """Create a provenance-rich manifest for outputs; does not publish or deploy."""
    output_records = []
    for output in blueprint.get("outputs", []):
        artifact = execution.outputs.get(output["id"])
        output_records.append({
            "output_id": output["id"],
            "product_type": output["product_type"],
            "experience": output["experience"],
            "delivery_targets": list(output.get("delivery_targets", [])),
            "release_policy": output.get("release_policy", {}),
            "artifact": (
                {
                    "artifact_id": artifact.get("artifact_id"),
                    "version": artifact.get("version"),
                    "checksum": artifact.get("checksum"),
                    "media_type": artifact.get("media_type"),
                    "size_bytes": artifact.get("size_bytes"),
                    "spatial": artifact.get("spatial"),
                    "rights": artifact.get("rights"),
                    "storage": artifact.get("storage"),
                }
                if artifact is not None
                else None
            ),
            "status": "assembled" if artifact is not None else "missing",
        })
    provenance = {
        "blueprint": {
            "id": blueprint["blueprint_id"],
            "version": blueprint["version"],
        },
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "compilation_fingerprint": compiled.get("compilation_fingerprint"),
        "recipe": execution.recipe,
        "execution_id": execution.execution_id,
        "execution_status": execution.status,
        "runs": {
            node_id: {
                "run_id": result.run.get("run_id"),
                "status": result.run.get("status"),
                "capability": result.run.get("capability"),
                "outputs": result.run.get("outputs", []),
                "provenance": result.run.get("provenance"),
            }
            for node_id, result in execution.node_results.items()
        },
    }
    manifest = {
        "manifest_version": "1.0.0",
        "product_id": blueprint["blueprint_id"],
        "product_version": blueprint["version"],
        "status": acceptance["status"],
        "release_allowed": acceptance["release_allowed"],
        "acceptance": acceptance,
        "outputs": output_records,
        "provenance": provenance,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
    manifest["manifest_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return manifest
