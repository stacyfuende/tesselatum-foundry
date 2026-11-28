"""Single customer transaction for registered spatial product templates.

This service composes the established intake, immutable Artifact, Blueprint,
Recipe Run, acceptance, manifest and export boundaries. It does not introduce
a second execution engine or bypass autonomy checks.
"""
from __future__ import annotations

from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.customer_ingestion import ingest_customer_geojson
from tessellatum_foundry.execution.customer_requests import prepare_customer_product_request
from tessellatum_foundry.execution.product_acceptance import (
    assemble_product_manifest,
    evaluate_product_acceptance,
)
from tessellatum_foundry.execution.product_delivery import build_geojson_product_bundle
from tessellatum_foundry.execution.product_execution import (
    compile_product_blueprint_recipe,
    execute_product_blueprint_plan,
)
from tessellatum_foundry.validation.contracts import ContractRegistry


def run_customer_spatial_product(
    request: dict[str, Any],
    source_bytes: bytes,
    *,
    artifact_store: Any,
    capabilities: CapabilityRegistry,
    recipe_service: Any,
    cell_templates: dict[str, dict[str, Any]],
    output_bindings: dict[str, dict[str, str]],
    actor_id: str,
    policy: dict[str, Any] | None = None,
    max_source_bytes: int = 25 * 1024 * 1024,
    max_source_features: int = 100_000,
    max_export_bytes: int = 100 * 1024 * 1024,
    contracts: ContractRegistry | None = None,
) -> dict[str, Any]:
    """Run one supported customer request through verified product delivery.

    The caller supplies the installed, reviewed Cell templates and output map.
    No template, capability, execution code, or output mapping is generated
    from customer input.
    """
    prepared = prepare_customer_product_request(
        request,
        capabilities=capabilities,
        policy=policy,
        contracts=contracts,
    )
    if prepared["status"] != "awaiting_source_ingestion":
        raise ValueError("Customer request is blocked and cannot be executed.")

    ingestion = ingest_customer_geojson(
        request,
        source_bytes,
        artifact_store=artifact_store,
        capabilities=capabilities,
        max_bytes=max_source_bytes,
        max_features=max_source_features,
    )
    blueprint = prepared["blueprint"]
    plan = prepared["execution_plan"]
    resolved_inputs = ingestion["resolved_input_bindings"]

    compiled = compile_product_blueprint_recipe(
        plan,
        cell_templates=cell_templates,
        capabilities=capabilities,
        resolved_input_bindings=resolved_inputs,
        output_bindings=output_bindings,
        contracts=contracts,
    )
    execution = execute_product_blueprint_plan(
        blueprint,
        plan,
        capabilities=capabilities,
        recipe_service=recipe_service,
        cell_templates=cell_templates,
        resolved_input_bindings=resolved_inputs,
        output_bindings=output_bindings,
        actor_id=actor_id,
        policy=policy,
        contracts=contracts,
    )
    acceptance = evaluate_product_acceptance(
        blueprint,
        execution,
        artifact_store=artifact_store,
    )
    manifest = assemble_product_manifest(
        blueprint,
        plan,
        compiled,
        execution,
        acceptance,
    )
    bundle = None
    if acceptance["release_allowed"]:
        bundle = build_geojson_product_bundle(
            manifest,
            artifact_store=artifact_store,
            max_output_bytes=max_export_bytes,
        )

    return {
        "request_id": request["request_id"],
        "status": "delivered" if bundle is not None else acceptance["status"],
        "customer_summary": prepared["customer_summary"],
        "source": {
            "artifact_id": ingestion["artifact"]["artifact_id"],
            "version": ingestion["artifact"]["version"],
            "checksum": ingestion["artifact"]["checksum"],
            "feature_count": ingestion["feature_count"],
            "source_bounds": ingestion["source_bounds"],
        },
        "execution": {
            "status": execution.status,
            "recipe_id": compiled["recipe"]["recipe_id"],
            "node_run_count": len(execution.node_results),
            "error": execution.error,
        },
        "acceptance": acceptance,
        "product_manifest": manifest,
        "delivery": {
            "media_type": "application/zip" if bundle is not None else None,
            "file_name": f"{request['request_id']}-product.zip" if bundle is not None else None,
            "content": bundle,
            "size_bytes": len(bundle) if bundle is not None else 0,
        },
    }
