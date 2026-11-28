"""Customer-language intake for supported Foundry spatial products.

This boundary translates a constrained request into a registered Blueprint plan.
It never generates capabilities, execution code, or unreviewed methods.
"""
from __future__ import annotations

from copy import deepcopy
import json
from importlib.resources import files
from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.product_blueprints import plan_product_blueprint
from tessellatum_foundry.validation.contracts import ContractRegistry


class CustomerProductRequestError(ValueError):
    """Raised when a customer request cannot be safely resolved."""


_SUPPORTED_JOB_TEMPLATES = {
    "standardize_site_coordinates": "nairobi-site-coordinate-standardization.json",
}


def prepare_customer_product_request(
    request: dict[str, Any],
    *,
    capabilities: CapabilityRegistry,
    policy: dict[str, Any] | None = None,
    contracts: ContractRegistry | None = None,
) -> dict[str, Any]:
    """Resolve a customer request to a safe, non-executing Blueprint plan.

    The uploaded file is not read or persisted here. The returned intake
    requirement explicitly describes the source file that must be ingested
    into an immutable Artifact before the existing execution handoff can run.
    """
    contracts = contracts or ContractRegistry()
    contracts.validate("customer_product_request.schema.json", request)

    template_name = _SUPPORTED_JOB_TEMPLATES.get(request["job_type"])
    if template_name is None:
        raise CustomerProductRequestError(
            "This request does not match an installed, approved product template."
        )
    template_resource = files("tessellatum_foundry").joinpath(
        "product_templates", template_name
    )
    try:
        blueprint = json.loads(template_resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise CustomerProductRequestError(
            "The approved product template is unavailable or invalid."
        ) from error
    if blueprint.get("metadata", {}).get("category") != "coordinate-standardization":
        raise CustomerProductRequestError(
            "The installed template is not registered for coordinate standardization."
        )

    resolved_blueprint = deepcopy(blueprint)
    file_name = request["source_file"]["file_name"]
    if "/" in file_name or chr(92) in file_name:
        raise CustomerProductRequestError("Source file name must not contain a path.")
    media_type = request["source_file"]["media_type"]
    if file_name.lower().endswith(".geojson") != (media_type == "application/geo+json"):
        raise CustomerProductRequestError(
            "Source file extension and declared media type do not match."
        )
    source_crs = request["source_file"]["coordinate_reference_system"]
    expected_crs = {"authority": "EPSG", "code": 4326}
    if source_crs != expected_crs:
        raise CustomerProductRequestError(
            "This product currently accepts GeoJSON coordinates declared as EPSG:4326."
        )

    resolved_blueprint["title"] = request.get(
        "product_name", resolved_blueprint["title"]
    )
    resolved_blueprint["intent"]["audience"] = request["audience"]
    resolved_blueprint["intent"]["decision_context"] = request["decision_context"]
    resolved_blueprint["intent"]["geographic_scope"] = {
        "description": request["geographic_scope"]
    }

    plan = plan_product_blueprint(
        resolved_blueprint,
        capabilities=capabilities,
        policy=policy,
        contracts=contracts,
    )
    if plan["status"] != "planned":
        status = "blocked"
        next_action = "Resolve the planning findings before accepting the source file."
    else:
        status = "awaiting_source_ingestion"
        next_action = (
            "Ingest and validate the supplied GeoJSON as an immutable Artifact; "
            "then bind it to the planned site-coordinate input before execution."
        )

    return {
        "request_id": request["request_id"],
        "status": status,
        "customer_summary": {
            "product_name": resolved_blueprint["title"],
            "outcome": resolved_blueprint["intent"]["outcome"],
            "audience": resolved_blueprint["intent"]["audience"],
            "decision_context": resolved_blueprint["intent"]["decision_context"],
            "geographic_scope": resolved_blueprint["intent"]["geographic_scope"]["description"],
            "delivery_format": "GeoJSON",
            "output_coordinate_reference_system": "EPSG:32737",
        },
        "source_requirement": {
            "file_name": request["source_file"]["file_name"],
            "media_type": request["source_file"]["media_type"],
            "coordinate_reference_system": "EPSG:4326",
            "coordinate_order": "longitude, latitude",
            "required_input": "site locations",
            "ingestion_required": True,
        },
        "next_action": next_action,
        # Keep the complete, validated Blueprint beside its compact plan summary.
        # Execution, acceptance and manifests need the full contract, not only identity.
        "blueprint": resolved_blueprint,
        "execution_plan": plan,
    }
