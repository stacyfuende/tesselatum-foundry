from copy import deepcopy

import pytest

from tessellatum_foundry.execution.autonomy import AutonomyPolicyError, evaluate_autonomy
from tessellatum_foundry.validation.contracts import ContractRegistry


@pytest.fixture
def policy():
    return {
        "policy_id": "default-product-policy",
        "version": "1.0.0",
        "default_mode": "automatic",
        "rules": [{
            "id": "high-uncertainty-review",
            "decision": "select-method",
            "mode": "guided",
            "when": {"uncertainty": "high"},
            "rationale": "Compare alternatives before selecting a method.",
        }],
        "hard_stops": [
            "external_publication", "sensitive_data_access",
            "irreversible_action", "recurring_billing",
        ],
        "record_decisions": True,
        "allow_user_override": True,
    }


def test_low_risk_routine_choice_is_automatic(policy):
    result = evaluate_autonomy("fit-layout", {"impact": "low", "reversibility": "reversible"}, policy)
    assert result["mode"] == "automatic"
    assert not result["requires_approval"]


def test_capability_profile_contributes_risk_baseline(policy):
    capability = {"autonomy": {"impact": "moderate", "reversibility": "reversible"}}
    result = evaluate_autonomy("read-source", {}, policy, capability=capability)
    assert result["context"]["impact"] == "moderate"
    assert result["mode"] == "automatic"


def test_irreversible_action_requires_explicit_authorisation(policy):
    result = evaluate_autonomy("publish", {"reversibility": "irreversible"}, policy)
    assert result["mode"] == "explicit"
    assert result["requires_approval"]


def test_external_publication_hard_stop_cannot_be_overridden(policy):
    result = evaluate_autonomy(
        "publish", {"external_publication": True}, policy, requested_mode="automatic"
    )
    assert result["mode"] == "explicit"
    assert result["hard_stops"] == ["external_publication"]


def test_user_can_request_more_caution(policy):
    assert evaluate_autonomy("fit-layout", {}, policy, requested_mode="guided")["mode"] == "guided"


def test_high_uncertainty_rule_matches_and_explains(policy):
    result = evaluate_autonomy("select-method", {"uncertainty": "high"}, policy)
    assert result["mode"] == "guided"
    assert result["matched_rules"] == ["high-uncertainty-review"]
    assert any("Compare alternatives" in reason for reason in result["reasons"])


def test_lower_risk_does_not_match_threshold_rule(policy):
    result = evaluate_autonomy("select-method", {"uncertainty": "low"}, policy)
    assert result["mode"] == "automatic"
    assert result["matched_rules"] == []


def test_capability_approval_requirement_wins(policy):
    capability = {"autonomy": {"approval_required": True}}
    result = evaluate_autonomy(
        "restricted-operation", {}, policy, capability=capability, requested_mode="automatic"
    )
    assert result["mode"] == "explicit"


def test_invalid_mode_is_rejected(policy):
    policy["default_mode"] = "magic"
    with pytest.raises(AutonomyPolicyError, match="default_mode"):
        evaluate_autonomy("anything", {}, policy)


def test_policy_schema_accepts_policy(policy):
    ContractRegistry().validate("autonomy_policy.schema.json", policy)


def test_evaluation_does_not_mutate_inputs(policy):
    context = {"impact": "low"}
    original = deepcopy(context)
    evaluate_autonomy("fit-layout", context, policy)
    assert context == original
