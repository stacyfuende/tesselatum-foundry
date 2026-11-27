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


class ExperimentExecutionError(RuntimeError):
    """Experiment execution could not produce a valid report."""


def execute_experiment(
    plans: list[dict[str, Any]],
    *,
    execute_variant: Any,
    compare_variants: Any | None = None,
) -> dict[str, Any]:
    """Execute bounded plans through a caller-supplied registered Run service.

    Callbacks are dependency injection for trusted capability services, not a
    facility for evaluating arbitrary user or LLM-generated code. Variant failures
    are captured so the experiment can report partial results. Optional comparison
    callbacks run only for successful variants and return JSON-compatible metrics.
    """
    if not isinstance(plans, list) or not plans or len(plans) > 100:
        raise ExperimentExecutionError("Execution requires 1 to 100 planned variants.")
    if not callable(execute_variant):
        raise ExperimentExecutionError("A registered variant execution callback is required.")
    outcomes = []
    successes = []
    for plan in plans:
        key = plan.get("variant_key")
        if not isinstance(key, str) or not key:
            raise ExperimentExecutionError("Each plan must have a stable variant_key.")
        try:
            result = execute_variant(deepcopy(plan["cell"]), deepcopy(plan))
            successes.append((plan, result))
            outcomes.append({
                "variant_key": key,
                "method_id": plan.get("method_id"),
                "method_label": plan.get("method_label"),
                "parameters": deepcopy(plan.get("parameters", {})),
                "status": "succeeded",
                "result": result,
            })
        except Exception as error:  # Capture per-variant failures for partial experiment reporting.
            outcomes.append({
                "variant_key": key,
                "method_id": plan.get("method_id"),
                "method_label": plan.get("method_label"),
                "parameters": deepcopy(plan.get("parameters", {})),
                "status": "failed",
                "error": {"type": type(error).__name__, "message": str(error)},
            })
    comparisons = []
    if compare_variants is not None:
        if not callable(compare_variants):
            raise ExperimentExecutionError("Comparison callback must be callable.")
        for index, (plan_a, result_a) in enumerate(successes):
            for plan_b, result_b in successes[index + 1:]:
                comparisons.append({
                    "variant_a": plan_a["variant_key"],
                    "variant_b": plan_b["variant_key"],
                    "metrics": compare_variants(result_a, result_b, deepcopy(plan_a), deepcopy(plan_b)),
                })
    return {
        "experiment_report_version": "1.0.0",
        "variant_count": len(plans),
        "succeeded": len(successes),
        "failed": len(plans) - len(successes),
        "variants": outcomes,
        "comparisons": comparisons,
    }
