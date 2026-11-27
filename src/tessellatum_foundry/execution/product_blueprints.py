"""Deterministic planning from Spatial Product Blueprints to registered capabilities."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator

from tessellatum_foundry.execution.autonomy import evaluate_autonomy
from tessellatum_foundry.execution.capabilities import CapabilityRegistry, CapabilityRegistryError
from tessellatum_foundry.validation.contracts import ContractRegistry


class ProductBlueprintPlanError(ValueError):
    """Raised when a Spatial Product Blueprint cannot be planned safely."""


_DEFAULT_POLICY = {
    "policy_id": "foundry-default",
    "version": "1.0.0",
    "default_mode": "automatic",
    "rules": [],
    "hard_stops": [
        "external_publication",
        "sensitive_data_access",
        "irreversible_action",
        "legal_commitment",
        "material_unbounded_cost",
        "recurring_billing",
    ],
    "record_decisions": True,
}


def plan_product_blueprint(
    blueprint: dict[str, Any],
    *,
    capabilities: CapabilityRegistry,
    policy: dict[str, Any] | None = None,
    contracts: ContractRegistry | None = None,
    requested_mode: str | None = None,
) -> dict[str, Any]:
    """Validate and compile a blueprint into a deterministic, non-executing plan.

    Input bindings use `node_id.output_port` for upstream outputs and
    `evidence:reference_id` for supplied evidence. Other strings are treated
    as externally supplied input handles. This function never creates Runs.
    """
    contracts = contracts or ContractRegistry()
    policy = deepcopy(policy if policy is not None else _DEFAULT_POLICY)
    blueprint = deepcopy(blueprint)
    contracts.validate("spatial_product_blueprint.schema.json", blueprint)
    contracts.validate("autonomy_policy.schema.json", policy)

    nodes = blueprint["reasoning"]["nodes"]
    node_by_id = {node["id"]: node for node in nodes}
    if len(node_by_id) != len(nodes):
        raise ProductBlueprintPlanError("Blueprint contains duplicate reasoning node IDs.")
    maximum = blueprint["reasoning"].get("max_nodes", 50)
    if len(nodes) > maximum:
        raise ProductBlueprintPlanError(
            f"Blueprint has {len(nodes)} nodes; configured maximum is {maximum}."
        )

    evidence_ids = {
        item["id"] for item in blueprint["evidence"].get("provided_references", [])
    }
    requirements = {
        item["id"]: item for item in blueprint["evidence"]["requirements"]
    }
    provided_references = blueprint["evidence"].get("provided_references", [])
    supplied_roles = {item.get("role") for item in provided_references}
    reference_by_id = {item["id"]: item for item in provided_references}
    if len(reference_by_id) != len(provided_references):
        raise ProductBlueprintPlanError("Blueprint contains duplicate evidence reference IDs.")
    if len(requirements) != len(blueprint["evidence"]["requirements"]):
        raise ProductBlueprintPlanError("Blueprint contains duplicate evidence requirement IDs.")
    missing_evidence = [
        {"id": item["id"], "role": item["role"], "required": item.get("required", True)}
        for item in requirements.values()
        if item.get("required", True) and item["role"] not in supplied_roles
    ]

    resolved: dict[str, dict[str, Any]] = {}
    missing_capabilities: list[dict[str, str]] = []
    findings: list[dict[str, str]] = []
    dependencies: dict[str, set[str]] = {node["id"]: set(node.get("depends_on", [])) for node in nodes}

    for node in nodes:
        node_id = node["id"]
        capability_id = node["capability"]
        try:
            if node.get("capability_version"):
                capability = capabilities.get(capability_id, node["capability_version"])
            else:
                raise ProductBlueprintPlanError(
                    f"Node {node_id!r} must pin an exact capability_version."
                )
        except CapabilityRegistryError:
            missing_capabilities.append({
                "node_id": node_id,
                "capability_id": capability_id,
                "version": node.get("capability_version", ""),
            })
            continue

        port_map = {port["port_id"]: port for port in capability.get("input_ports", [])}
        bindings = node.get("inputs", {})
        unknown_ports = sorted(set(bindings) - set(port_map))
        if unknown_ports:
            findings.append({
                "code": "unknown_input_port",
                "node_id": node_id,
                "message": "Unknown input port(s): " + ", ".join(unknown_ports),
            })
        for port_id, port in port_map.items():
            if port.get("required", True) and port_id not in bindings:
                findings.append({
                    "code": "unbound_required_input",
                    "node_id": node_id,
                    "message": f"Required input {port_id!r} is not bound.",
                })

        for port_id, source in bindings.items():
            if source.startswith("evidence:"):
                reference_id = source.split(":", 1)[1]
                reference = reference_by_id.get(reference_id)
                if reference is None:
                    findings.append({
                        "code": "unresolved_evidence",
                        "node_id": node_id,
                        "message": f"Evidence reference {reference_id!r} is not supplied.",
                    })
                elif not reference.get("role"):
                    findings.append({
                        "code": "evidence_role_missing",
                        "node_id": node_id,
                        "message": f"Evidence reference {reference_id!r} has no declared role.",
                    })
            elif "." in source:
                source_node, output_port = source.split(".", 1)
                if source_node not in node_by_id:
                    findings.append({
                        "code": "unknown_dependency",
                        "node_id": node_id,
                        "message": f"Input {port_id!r} references unknown node {source_node!r}.",
                    })
                else:
                    dependencies[node_id].add(source_node)

        for dependency in dependencies[node_id]:
            if dependency not in node_by_id:
                findings.append({
                    "code": "unknown_dependency",
                    "node_id": node_id,
                    "message": f"Dependency {dependency!r} does not exist.",
                })

        parameter_schema = capability.get("parameter_schema", {"type": "object"})
        parameter_errors = sorted(
            Draft202012Validator(parameter_schema).iter_errors(node.get("parameters", {})),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        for error in parameter_errors:
            findings.append({
                "code": "invalid_parameters",
                "node_id": node_id,
                "message": f"Parameters: {error.message}",
            })

        resolved[node_id] = {"capability": capability, "bindings": bindings}

    # Validate upstream ports after every node has been resolved, independent of declaration order.
    for node in nodes:
        node_id = node["id"]
        target = resolved.get(node_id)
        if target is None:
            continue
        target_ports = {
            port["port_id"]: port
            for port in target["capability"].get("input_ports", [])
        }
        for port_id, source in node.get("inputs", {}).items():
            if "." not in source or source.startswith("evidence:"):
                continue
            source_node, output_port = source.split(".", 1)
            upstream = resolved.get(source_node)
            if upstream is None:
                continue
            source_ports = {
                port["port_id"]: port
                for port in upstream["capability"].get("output_ports", [])
            }
            source_port = source_ports.get(output_port)
            if source_port is None:
                findings.append({
                    "code": "unknown_output_port",
                    "node_id": node_id,
                    "message": f"Node {source_node!r} has no output port {output_port!r}.",
                })
                continue
            target_kind = target_ports.get(port_id, {}).get("data_kind")
            source_kind = source_port.get("data_kind")
            if target_kind not in {None, "any"} and source_kind not in {target_kind, "any"}:
                findings.append({
                    "code": "incompatible_data_kind",
                    "node_id": node_id,
                    "message": (
                        f"Input {port_id!r} expects {target_kind!r}, but "
                        f"{source_node}.{output_port} produces {source_kind!r}."
                    ),
                })

    if missing_capabilities:
        findings.extend({
            "code": "missing_capability",
            "node_id": item["node_id"],
            "message": f"Capability {item['capability_id']}@{item['version'] or 'unpinned'} is not registered.",
        } for item in missing_capabilities)

    order: list[str] = []
    if not any(item["code"] == "unknown_dependency" for item in findings):
        indegree = {node_id: len(dependencies[node_id]) for node_id in node_by_id}
        downstream: dict[str, set[str]] = defaultdict(set)
        for node_id, parents in dependencies.items():
            for parent in parents:
                if parent in downstream:
                    downstream[parent].add(node_id)
        ready = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
        while ready:
            current = ready.popleft()
            order.append(current)
            for child in sorted(downstream[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(order) != len(nodes):
            findings.append({
                "code": "dependency_cycle",
                "node_id": "",
                "message": "Reasoning dependencies contain a directed cycle.",
            })

    decisions = []
    for node_id in order:
        if node_id not in resolved:
            continue
        capability = resolved[node_id]["capability"]
        decision = evaluate_autonomy(
            "execute-capability",
            {"impact": "moderate", "uncertainty": "moderate"},
            policy,
            capability=capability,
            requested_mode=requested_mode,
        )
        decisions.append({"node_id": node_id, **decision})

    for output in blueprint["outputs"]:
        release = output.get("release_policy", {})
        # Delivery targets represent a release boundary. Never let a false
        # approval_required flag suppress policy evaluation for external delivery.
        if output.get("delivery_targets") or release.get("approval_required"):
            decisions.append({
                "node_id": output["id"],
                **evaluate_autonomy(
                    "external-publication",
                    {
                        "external_publication": bool(output.get("delivery_targets")),
                        "impact": "moderate",
                    },
                    policy,
                    requested_mode=requested_mode,
                ),
            })

    blocking = bool(findings or missing_evidence)
    approval_required = any(item["requires_approval"] for item in decisions)
    capability_fingerprints = {
        node_id: hashlib.sha256(json.dumps(
            resolved[node_id]["capability"], sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        for node_id in sorted(resolved)
    }
    plan_material = {
        "blueprint": blueprint,
        "policy": policy,
        "capabilities": capability_fingerprints,
    }
    plan_fingerprint = hashlib.sha256(json.dumps(
        plan_material, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {
        "plan_fingerprint": plan_fingerprint,
        "blueprint": {
            "blueprint_id": blueprint["blueprint_id"],
            "version": blueprint["version"],
            "title": blueprint["title"],
        },
        "status": "blocked" if blocking else ("approval_required" if approval_required else "planned"),
        "approval_required": approval_required,
        "executable": False,
        "execution_note": "Planning only: no Runs, artifacts, deployments, or publications were created.",
        "node_order": order,
        "nodes": [
            {
                "node_id": node_id,
                "capability_id": resolved[node_id]["capability"]["capability_id"],
                "capability_version": resolved[node_id]["capability"]["version"],
                "bindings": resolved[node_id]["bindings"],
                "parameters": deepcopy(node_by_id[node_id].get("parameters", {})),
            }
            for node_id in order if node_id in resolved
        ],
        "outputs": deepcopy(blueprint["outputs"]),
        "autonomy_decisions": decisions,
        "missing_capabilities": missing_capabilities,
        "missing_evidence": missing_evidence,
        "findings": findings,
        "acceptance_checks": deepcopy(blueprint["acceptance"]["checks"]),
        "resource_limits": deepcopy(blueprint.get("resource_limits", {})),
    }
