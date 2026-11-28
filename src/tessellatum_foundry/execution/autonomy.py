"""Deterministic autonomy decisions for registered Foundry capabilities."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


class AutonomyPolicyError(ValueError):
    """Invalid autonomy policy or decision context."""


_LEVEL = {"automatic": 0, "guided": 1, "explicit": 2}
_ORDERED = {
    "impact": ["low", "moderate", "high", "critical"],
    "reversibility": ["reversible", "costly_to_reverse", "irreversible"],
    "uncertainty": ["low", "moderate", "high"],
    "sensitivity": ["none", "personal", "commercial", "regulated"],
    "cost_band": ["negligible", "bounded", "material", "unknown"],
}


def _mode(value: Any, label: str) -> str:
    if value not in _LEVEL:
        raise AutonomyPolicyError(f"{label} must be automatic, guided, or explicit.")
    return value


def _matches(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    for key, expected in conditions.items():
        actual = context.get(key)
        if key in _ORDERED:
            if actual not in _ORDERED[key] or expected not in _ORDERED[key]:
                return False
            if _ORDERED[key].index(actual) < _ORDERED[key].index(expected):
                return False
        elif actual != expected:
            return False
    return True


def evaluate_autonomy(
    decision: str,
    context: dict[str, Any],
    policy: dict[str, Any],
    *,
    capability: dict[str, Any] | None = None,
    requested_mode: str | None = None,
) -> dict[str, Any]:
    """Resolve a safe autonomy level; stricter requirements always win.

    Ordered rule values are minimum thresholds. Missing context never satisfies
    a threshold. Capability declarations contribute a conservative risk baseline.
    """
    if not isinstance(decision, str) or not decision.strip():
        raise AutonomyPolicyError("decision must be a non-empty string.")
    if not isinstance(context, dict) or not isinstance(policy, dict):
        raise AutonomyPolicyError("context and policy must be objects.")
    mode = _mode(policy.get("default_mode"), "default_mode")
    resolved = deepcopy(context)
    reasons: list[str] = []
    matched: list[str] = []

    if capability is not None:
        profile = capability.get("autonomy", {})
        if not isinstance(profile, dict):
            raise AutonomyPolicyError("capability autonomy declaration must be an object.")
        required_profile = {
            "impact", "reversibility", "uncertainty", "sensitivity",
            "cost_band", "side_effect", "external_access", "approval_required",
        }
        missing_profile = sorted(required_profile - profile.keys())
        if missing_profile:
            mode = max((mode, "guided"), key=_LEVEL.get)
            reasons.append(
                "Incomplete capability autonomy declaration; guided review required: "
                + ", ".join(missing_profile)
                + "."
            )
        for key, levels in _ORDERED.items():
            declared, observed = profile.get(key), resolved.get(key)
            if declared in levels:
                resolved[key] = max(
                    (declared, observed) if observed in levels else (declared,),
                    key=levels.index,
                )
        if profile.get("approval_required") is True:
            mode = "explicit"
            reasons.append("Capability contract requires explicit approval.")
        if profile.get("side_effect") in {"external_write", "irreversible"}:
            resolved["irreversible_action"] = True
        if profile.get("external_access") is True:
            resolved["external_access"] = True

    impact = resolved.get("impact")
    if impact in {"high", "critical"}:
        mode = "explicit" if impact == "critical" else max((mode, "guided"), key=_LEVEL.get)
        reasons.append(f"{impact.title()} impact requires additional control.")
    if resolved.get("reversibility") == "irreversible":
        mode = "explicit"
        reasons.append("Irreversible action requires explicit authorisation.")
    if resolved.get("sensitivity") == "regulated":
        mode = "explicit"
        reasons.append("Regulated data requires explicit authorisation.")
    elif resolved.get("sensitivity") in {"personal", "commercial"}:
        mode = max((mode, "guided"), key=_LEVEL.get)
        reasons.append("Sensitive information requires guided handling.")
    if resolved.get("cost_band") in {"material", "unknown"}:
        mode = max((mode, "guided"), key=_LEVEL.get)
        reasons.append("Material or unknown cost requires review.")
    if resolved.get("uncertainty") == "high":
        mode = max((mode, "guided"), key=_LEVEL.get)
        reasons.append("High uncertainty requires review of assumptions.")

    for rule in policy.get("rules", []):
        if not isinstance(rule, dict):
            raise AutonomyPolicyError("Each policy rule must be an object.")
        if rule.get("decision") not in {decision, "*"}:
            continue
        conditions = rule.get("when", {})
        if not isinstance(conditions, dict):
            raise AutonomyPolicyError("Rule when conditions must be an object.")
        if _matches(conditions, resolved):
            rule_mode = _mode(rule.get("mode"), "rule mode")
            if _LEVEL[rule_mode] > _LEVEL[mode]:
                mode = rule_mode
            matched.append(rule.get("id", "unnamed"))
            if rule.get("rationale"):
                reasons.append(rule["rationale"])

    hard_stops = set(policy.get("hard_stops", []))
    candidates = []
    for key in (
        "external_publication", "sensitive_data_access", "irreversible_action",
        "legal_commitment", "recurring_billing",
    ):
        if resolved.get(key):
            candidates.append(key)
    if resolved.get("cost_band") == "unknown" and resolved.get("unbounded_cost"):
        candidates.append("material_unbounded_cost")
    triggered = sorted(set(candidates) & hard_stops)
    if triggered:
        mode = "explicit"
        reasons.append("Policy hard stop: " + ", ".join(triggered) + ".")

    if requested_mode is not None:
        requested_mode = _mode(requested_mode, "requested_mode")
        if _LEVEL[requested_mode] > _LEVEL[mode]:
            mode = requested_mode
            reasons.append("User requested a more cautious autonomy mode.")
        elif _LEVEL[requested_mode] < _LEVEL[mode]:
            reasons.append("A less cautious preference cannot bypass mandatory safeguards.")

    return {
        "decision": decision,
        "mode": mode,
        "requires_approval": mode == "explicit",
        "context": resolved,
        "matched_rules": matched,
        "hard_stops": triggered,
        "reasons": list(dict.fromkeys(reasons)) or [
            "Policy default applies; no escalation matched."
        ],
        "record_decision": policy.get("record_decisions", True),
    }
