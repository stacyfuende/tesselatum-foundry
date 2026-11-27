"""Compile validated Product Blueprint plans into the existing Recipe Run service."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.product_blueprints import plan_product_blueprint
from tessellatum_foundry.execution.recipes import (
    RecipeExecutionPreconditionError,
    RecipeExecutionResult,
    RecipeExecutionService,
)
from tessellatum_foundry.validation.contracts import ContractRegistry
from tessellatum_foundry.validation.graph import validate_recipe_graph


class ProductExecutionPreconditionError(ValueError):
    """Raised when a planned product cannot safely enter the Run service."""


def compile_product_blueprint_recipe(
    plan: dict[str, Any],
    *,
    cell_templates: dict[str, dict[str, Any]],
    capabilities: CapabilityRegistry,
    resolved_input_bindings: dict[str, dict[str, Any]],
    output_bindings: dict[str, dict[str, str]],
    contracts: ContractRegistry | None = None,
) -> dict[str, Any]:
    """Compile a plan into validated Cells and a Recipe without persisting or executing.

    Every non-upstream input must be supplied as a schema-valid immutable Cell
    binding keyed by "node_id.input_port". Upstream references are compiled
    into exact Cell-output bindings. Output bindings map each blueprint output
    ID to a reasoning node and its declared output port.
    """
    contracts = contracts or ContractRegistry()
    if plan.get("status") != "planned" or plan.get("approval_required"):
        raise ProductExecutionPreconditionError(
            "Only fully planned blueprints without pending approval can be compiled for execution."
        )
    if not plan.get("plan_fingerprint") or not re.fullmatch(
        r"[a-f0-9]{64}", plan["plan_fingerprint"]
    ):
        raise ProductExecutionPreconditionError("Plan fingerprint is missing or invalid.")

    nodes = plan.get("nodes", [])
    if set(cell_templates) != {node["node_id"] for node in nodes}:
        raise ProductExecutionPreconditionError(
            "Cell templates must be supplied for every planned node and no others."
        )
    if not nodes or len({node["node_id"] for node in nodes}) != len(nodes):
        raise ProductExecutionPreconditionError("Plan nodes are empty or contain duplicate IDs.")
    node_ids = {node["node_id"] for node in nodes}
    fingerprint = plan["plan_fingerprint"]
    try:
        compilation_fingerprint = hashlib.sha256(json.dumps(
            {
                "plan_fingerprint": fingerprint,
                "cell_templates": cell_templates,
                "resolved_input_bindings": resolved_input_bindings,
                "output_bindings": output_bindings,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as error:
        raise ProductExecutionPreconditionError(
            "Resolved execution inputs must be canonical JSON data."
        ) from error
    cell_refs: dict[str, dict[str, str]] = {}
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    capability_map: dict[tuple[str, str], dict[str, Any]] = {}
    consumed_input_bindings: set[str] = set()

    for node in nodes:
        node_id = node["node_id"]
        template = deepcopy(cell_templates.get(node_id, {}))
        capability_id = node["capability_id"]
        version = node["capability_version"]
        try:
            capability = capabilities.get(capability_id, version)
        except ValueError as error:
            raise ProductExecutionPreconditionError(str(error)) from error
        if template.get("capability") != {
            "capability_id": capability_id,
            "version": version,
        }:
            raise ProductExecutionPreconditionError(
                f"Cell template for {node_id!r} does not target {capability_id}@{version}."
            )

        cell_id = "bp-" + hashlib.sha256(
            f"{compilation_fingerprint}:{node_id}".encode("utf-8")
        ).hexdigest()[:32]
        cell_ref = {"cell_id": cell_id, "version": "1.0.0"}
        cell_refs[node_id] = cell_ref
        inputs: dict[str, Any] = {}
        for port_id, source in node.get("bindings", {}).items():
            if "." in source and not source.startswith("evidence:"):
                upstream_id, output_port = source.split(".", 1)
                if upstream_id not in node_ids:
                    raise ProductExecutionPreconditionError(
                        f"Input {node_id}.{port_id} references unknown node {upstream_id!r}."
                    )
                inputs[port_id] = {
                    "source": "cell_output",
                    "cell_id": cell_refs.get(upstream_id, {}).get("cell_id")
                    or "bp-" + hashlib.sha256(
                        f"{compilation_fingerprint}:{upstream_id}".encode("utf-8")
                    ).hexdigest()[:32],
                    "cell_version": "1.0.0",
                    "output_port": output_port,
                }
            else:
                key = f"{node_id}.{port_id}"
                binding = resolved_input_bindings.get(key)
                if binding is None:
                    raise ProductExecutionPreconditionError(
                        f"Input {key!r} has not been resolved to an immutable Artifact or typed external source."
                    )
                consumed_input_bindings.add(key)
                if source.startswith("evidence:"):
                    evidence_id = source.split(":", 1)[1]
                    reference = next(
                        (
                            item for item in plan.get("evidence", {}).get("provided_references", [])
                            if item["id"] == evidence_id
                        ),
                        None,
                    )
                    if (
                        reference is None
                        or binding.get("source") != "external"
                        or binding.get("reference", {}).get("uri") != reference["uri"]
                    ):
                        raise ProductExecutionPreconditionError(
                            f"Evidence binding {key!r} does not preserve the supplied reference URI."
                        )
                inputs[port_id] = deepcopy(binding)

        output_ports = {
            port["port_id"]: port for port in capability.get("output_ports", [])
        }
        template_outputs = template.get("output_contracts", {})
        if set(template_outputs) != set(output_ports):
            raise ProductExecutionPreconditionError(
                f"Cell template for {node_id!r} must declare every exact capability output port."
            )
        output_contracts = {}
        for port_id, port in output_ports.items():
            contract = deepcopy(template_outputs[port_id])
            if contract.get("data_kind") != port["data_kind"]:
                raise ProductExecutionPreconditionError(
                    f"Cell template output {node_id}.{port_id} has an incompatible data kind."
                )
            spatial = port.get("spatial", {})
            if (
                port["data_kind"] in {"vector", "raster", "point_cloud", "mesh"}
                or spatial.get("crs_required")
            ) and contract.get("crs") is None:
                raise ProductExecutionPreconditionError(
                    f"Cell template output {node_id}.{port_id} must declare its CRS."
                )
            allowed_geometry_types = set(spatial.get("geometry_types", []))
            declared_geometry_types = set(contract.get("geometry_types", []))
            if allowed_geometry_types and (
                not declared_geometry_types
                or not declared_geometry_types.issubset(allowed_geometry_types)
            ):
                raise ProductExecutionPreconditionError(
                    f"Cell template output {node_id}.{port_id} has missing or unsupported geometry types."
                )
            allowed_media_types = set(port.get("media_types", []))
            declared_media_types = set(contract.get("media_types", []))
            if declared_media_types and allowed_media_types and not declared_media_types.issubset(allowed_media_types):
                raise ProductExecutionPreconditionError(
                    f"Cell template output {node_id}.{port_id} declares unsupported media types."
                )
            output_contracts[port_id] = contract

        cell = {
            "cell_id": cell_id,
            "version": "1.0.0",
            "capability": {"capability_id": capability_id, "version": version},
            "inputs": inputs,
            "parameters": deepcopy(node.get("parameters", {})),
            "output_contracts": output_contracts,
        }
        for optional in ("constraints", "validation_requirements"):
            if optional in template:
                cell[optional] = deepcopy(template[optional])
        contracts.validate("cell.schema.json", cell)
        key = (cell_id, "1.0.0")
        cells[key] = cell
        capability_map[(capability_id, version)] = capability

    if set(resolved_input_bindings) != consumed_input_bindings:
        unused = sorted(set(resolved_input_bindings) - consumed_input_bindings)
        raise ProductExecutionPreconditionError(
            "Resolved input bindings contain unused entries: " + ", ".join(unused)
        )

    recipe_edges = []
    for node in nodes:
        for port_id, source in node.get("bindings", {}).items():
            if "." not in source or source.startswith("evidence:"):
                continue
            upstream_id, output_port = source.split(".", 1)
            recipe_edges.append({
                "from": {"node_id": upstream_id, "output_port": output_port},
                "to": {"node_id": node["node_id"], "input_port": port_id},
            })

    declared_outputs = []
    expected_output_ids = {item["id"] for item in plan.get("outputs", [])}
    if set(output_bindings) != expected_output_ids:
        raise ProductExecutionPreconditionError(
            "Every declared product output must map to exactly one reasoning node output."
        )
    for output_id, binding in sorted(output_bindings.items()):
        node_id, output_port = binding.get("node_id"), binding.get("output_port")
        if node_id not in node_ids:
            raise ProductExecutionPreconditionError(
                f"Product output {output_id!r} references unknown node {node_id!r}."
            )
        declared_outputs.append({
            "name": output_id,
            "node_id": node_id,
            "output_port": output_port,
        })

    blueprint = plan.get("blueprint", {})
    recipe = {
        "recipe_id": "product-" + re.sub(r"[^A-Za-z0-9._-]", "-", blueprint["blueprint_id"])[:100] + "-" + compilation_fingerprint[:12],
        "version": blueprint["version"],
        "title": blueprint["title"],
        "nodes": [
            {"node_id": node["node_id"], "cell": cell_refs[node["node_id"]]}
            for node in nodes
        ],
        "edges": recipe_edges,
        "declared_outputs": declared_outputs,
        "metadata": {
            "product_plan_fingerprint": fingerprint,
            "compilation_fingerprint": compilation_fingerprint,
        },
    }
    contracts.validate("recipe.schema.json", recipe)
    graph_findings = validate_recipe_graph(
        recipe, cells=cells, capabilities=capability_map
    )
    if graph_findings:
        detail = "; ".join(
            f"{finding.code}: {finding.message}" for finding in graph_findings
        )
        raise ProductExecutionPreconditionError(
            f"Compiled Recipe failed graph validation: {detail}"
        )

    return {
        "recipe": recipe,
        "cells": cells,
        "capabilities": capability_map,
        "plan_fingerprint": fingerprint,
        "compilation_fingerprint": compilation_fingerprint,
    }


def execute_product_blueprint_plan(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
    *,
    capabilities: CapabilityRegistry,
    recipe_service: RecipeExecutionService,
    cell_templates: dict[str, dict[str, Any]],
    resolved_input_bindings: dict[str, dict[str, Any]],
    output_bindings: dict[str, dict[str, str]],
    actor_id: str,
    policy: dict[str, Any] | None = None,
    requested_mode: str | None = None,
    contracts: ContractRegistry | None = None,
) -> RecipeExecutionResult:
    """Re-plan, fail closed on review gates, then hand the compiled Recipe to Run service."""
    fresh_plan = plan_product_blueprint(
        blueprint, capabilities=capabilities, policy=policy,
        requested_mode=requested_mode, contracts=contracts
    )
    if fresh_plan["plan_fingerprint"] != plan.get("plan_fingerprint"):
        raise ProductExecutionPreconditionError(
            "Blueprint plan is stale; re-plan against the current policy and capability registry."
        )
    if fresh_plan["status"] != "planned" or fresh_plan["approval_required"]:
        raise ProductExecutionPreconditionError(
            "Blueprint is blocked or requires explicit authorisation; no Runs were started."
        )
    if any(
        decision.get("mode") != "automatic"
        for decision in fresh_plan.get("autonomy_decisions", [])
    ):
        raise ProductExecutionPreconditionError(
            "Guided or explicit decisions must be resolved before execution; no Runs were started."
        )

    compiled = compile_product_blueprint_recipe(
        fresh_plan,
        cell_templates=cell_templates,
        capabilities=capabilities,
        resolved_input_bindings=resolved_input_bindings,
        output_bindings=output_bindings,
        contracts=contracts,
    )
    try:
        return recipe_service.execute(
            recipe=compiled["recipe"],
            cells=compiled["cells"],
            capabilities=compiled["capabilities"],
            actor_id=actor_id,
        )
    except RecipeExecutionPreconditionError as error:
        raise ProductExecutionPreconditionError(str(error)) from error
