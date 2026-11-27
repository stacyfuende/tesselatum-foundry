"""Deterministic planning for method and parameter experiments; no code execution."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from itertools import product
from typing import Any


class ExperimentPlanError(ValueError):
    """Invalid or excessive experiment expansion."""


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overrides.items():
        result[key] = deepcopy(value)
    return result


def plan_experiment(
    experiment: dict[str, Any],
    cell_template: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand methods × parameter axes into immutable, hash-keyed variant plans.

    Plans are declarations only: execution remains delegated to the registered
    capability Run service. This planner never evaluates user/LLM-generated code.
    """
    if not isinstance(experiment, dict) or not isinstance(cell_template, dict):
        raise ExperimentPlanError("Experiment and Cell template must be objects.")
    axes = experiment.get("parameter_axes", {})
    if not isinstance(axes, dict):
        raise ExperimentPlanError("parameter_axes must be an object.")
    axis_names = sorted(axes)
    axis_values = []
    for name in axis_names:
        values = axes[name]
        if not isinstance(values, list) or not values:
            raise ExperimentPlanError(f"Parameter axis {name!r} must be non-empty.")
        axis_values.append(values)
    methods = experiment.get("methods", [])
    if not isinstance(methods, list) or not methods:
        raise ExperimentPlanError("At least one method is required.")
    max_variants = experiment.get("max_variants", 50)
    if isinstance(max_variants, bool) or not isinstance(max_variants, int) or max_variants < 1:
        raise ExperimentPlanError("max_variants must be a positive integer.")
    combinations = list(product(*axis_values)) if axis_values else [()]
    count = len(combinations) * len(methods)
    if count > max_variants or count > 100:
        raise ExperimentPlanError(
            f"Expansion would create {count} variants; limit is {min(max_variants, 100)}."
        )
    base_parameters = experiment.get("baseline_parameters", {})
    if not isinstance(base_parameters, dict):
        raise ExperimentPlanError("baseline_parameters must be an object.")
    plans = []
    seen_ids = set()
    for method in methods:
        method_id = method.get("method_id")
        if not isinstance(method_id, str) or not method_id.strip():
            raise ExperimentPlanError("Each method requires a non-empty method_id.")
        for values in combinations:
            axis_overrides = dict(zip(axis_names, values))
            parameters = _merge(
                _merge(base_parameters, method.get("parameter_overrides", {})),
                axis_overrides,
            )
            cell = deepcopy(cell_template)
            cell["parameters"] = parameters
            if method.get("capability") is not None:
                cell["capability"] = deepcopy(method["capability"])
            variant_payload = {
                "experiment_id": experiment.get("experiment_id"),
                "experiment_version": experiment.get("version"),
                "method_id": method_id,
                "parameters": parameters,
                "capability": cell.get("capability"),
                "cell_template": experiment.get("cell_template"),
            }
            canonical = json.dumps(variant_payload, sort_keys=True, separators=(",", ":"))
            variant_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if variant_key in seen_ids:
                raise ExperimentPlanError("Experiment produces duplicate variant definitions.")
            seen_ids.add(variant_key)
            plans.append({
                "variant_key": variant_key,
                "method_id": method_id,
                "method_label": method.get("label", method_id),
                "evidence": deepcopy(method.get("evidence", [])),
                "parameter_overrides": axis_overrides,
                "parameters": parameters,
                "cell": cell,
            })
    return plans
