"""Tests for deterministic method/parameter experiment planning."""

from copy import deepcopy

import pytest

from tessellatum_foundry.execution.experiments import (
    ExperimentPlanError,
    plan_experiment,
)
from tessellatum_foundry.validation.contracts import (
    ContractRegistry,
    ContractValidationError,
)


@pytest.fixture
def experiment():
    return {
        "experiment_id": "threshold-comparison",
        "version": "1.0.0",
        "cell_template": {"cell_id": "measure", "version": "1.0.0"},
        "baseline_parameters": {"threshold": 0.5, "method_detail": "default"},
        "parameter_axes": {"threshold": [0.2, 0.5, 0.8], "scale": [10, 20]},
        "methods": [
            {"method_id": "baseline", "label": "Baseline"},
            {
                "method_id": "paper-method",
                "label": "Paper method",
                "parameter_overrides": {"method_detail": "paper"},
                "evidence": [{"type": "paper", "reference": "doi:10.1234/example"}],
            },
        ],
        "max_variants": 20,
    }


@pytest.fixture
def cell():
    return {
        "cell_id": "measure",
        "version": "1.0.0",
        "capability": {"capability_id": "vector.buffer", "version": "1.0.0"},
        "inputs": {},
        "parameters": {},
        "output_contracts": {"result": {"data_kind": "vector"}},
    }


def test_expand_method_and_parameter_cartesian_product(experiment, cell):
    plans = plan_experiment(experiment, cell)
    assert len(plans) == 12
    assert {plan["method_id"] for plan in plans} == {"baseline", "paper-method"}
    assert {plan["parameters"]["threshold"] for plan in plans} == {0.2, 0.5, 0.8}
    assert {plan["parameters"]["scale"] for plan in plans} == {10, 20}
    assert all(plan["cell"]["parameters"] == plan["parameters"] for plan in plans)


def test_variant_keys_are_deterministic_and_change_with_parameters(experiment, cell):
    first = plan_experiment(experiment, cell)
    second = plan_experiment(deepcopy(experiment), deepcopy(cell))
    assert [item["variant_key"] for item in first] == [item["variant_key"] for item in second]
    experiment["parameter_axes"]["threshold"] = [0.25, 0.5, 0.8]
    third = plan_experiment(experiment, cell)
    assert first[0]["variant_key"] != third[0]["variant_key"]


def test_method_evidence_attaches_to_variant(experiment, cell):
    paper_plan = next(
        item for item in plan_experiment(experiment, cell)
        if item["method_id"] == "paper-method"
    )
    assert paper_plan["evidence"][0]["reference"] == "doi:10.1234/example"


def test_variant_limit_prevents_unbounded_expansion(experiment, cell):
    experiment["max_variants"] = 5
    with pytest.raises(ExperimentPlanError, match="limit"):
        plan_experiment(experiment, cell)


def test_empty_axis_and_duplicate_method_definition_rejected(experiment, cell):
    experiment["parameter_axes"]["threshold"] = []
    with pytest.raises(ExperimentPlanError):
        plan_experiment(experiment, cell)
    experiment["parameter_axes"]["threshold"] = [0.5]
    experiment["methods"] = [experiment["methods"][0], deepcopy(experiment["methods"][0])]
    with pytest.raises(ExperimentPlanError, match="duplicate"):
        plan_experiment(experiment, cell)


def test_planner_does_not_mutate_cell_template(experiment, cell):
    original = deepcopy(cell)
    plan_experiment(experiment, cell)
    assert cell == original


def test_experiment_manifest_schema_accepts_fixture(experiment):
    ContractRegistry().validate("experiment.schema.json", experiment)


def test_experiment_manifest_schema_rejects_overlarge_variant_limit(experiment):
    experiment["max_variants"] = 101
    with pytest.raises(ContractValidationError):
        ContractRegistry().validate("experiment.schema.json", experiment)
