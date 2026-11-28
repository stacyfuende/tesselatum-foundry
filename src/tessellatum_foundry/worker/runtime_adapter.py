"""Adapter for composing existing LocalFoundry services into customer-job runtime contracts.

This is an explicit composition boundary. It does not construct tenant storage,
invent capability templates, or provision durable services.
"""
from __future__ import annotations

from typing import Any


def adapt_local_foundry_runtime(
    foundry: Any,
    *,
    cell_templates: dict[str, dict[str, Any]],
    output_bindings: dict[str, dict[str, str]],
    policy: dict[str, Any] | None = None,
    max_export_bytes: int = 100 * 1024 * 1024,
) -> dict[str, Any]:
    """Expose existing LocalFoundry services in the worker's runtime shape.

    Callers must supply reviewed, installed templates and output bindings.
    """
    if not isinstance(cell_templates, dict) or not cell_templates:
        raise ValueError("cell_templates must be a non-empty mapping.")
    if not isinstance(output_bindings, dict) or not output_bindings:
        raise ValueError("output_bindings must be a non-empty mapping.")
    if isinstance(max_export_bytes, bool) or not isinstance(max_export_bytes, int) or max_export_bytes < 1:
        raise ValueError("max_export_bytes must be a positive integer.")
    required_attributes = ("artifacts", "capabilities", "recipes", "contracts")
    missing = [name for name in required_attributes if not hasattr(foundry, name)]
    if missing:
        raise ValueError("LocalFoundry composition is incomplete: " + ", ".join(missing))
    runtime = {
        "artifact_store": foundry.artifacts,
        "capabilities": foundry.capabilities,
        "recipe_service": foundry.recipes,
        "cell_templates": cell_templates,
        "output_bindings": output_bindings,
        "contracts": foundry.contracts,
        "max_export_bytes": max_export_bytes,
    }
    if policy is not None:
        runtime["policy"] = policy
    return runtime
