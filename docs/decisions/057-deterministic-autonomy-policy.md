# ADR-057: Deterministic autonomy policy for capability orchestration

## Status
Proposed for review on PR #24

## Context
An outcome-first product factory must hide routine mechanics without hiding consequential choices. Asking an LLM to decide when it should ask for permission is not an adequate safety boundary. Capabilities already have canonical, versioned contracts; those contracts can declare operational characteristics that a deterministic policy evaluator uses.

## Decision
Introduce a deterministic autonomy evaluator with three modes:

- **Automatic:** Foundry may proceed within declared bounds.
- **Guided:** Foundry recommends, explains trade-offs, and supports comparison or user selection.
- **Explicit:** a human authorisation is required before the action proceeds.

The evaluator considers decision context, capability-declared risk, policy rules, and hard stops. Ordered dimensions use minimum thresholds: a rule for high uncertainty matches high uncertainty, not low or moderate uncertainty. Missing context does not satisfy a threshold.

Capability contracts may declare:
- impact, reversibility, uncertainty, sensitivity, and cost band;
- side-effect class and external access;
- whether approval is always required.

Capability risk is combined conservatively with request context. The stricter mode wins. A user may request more caution; a less cautious preference cannot bypass mandatory safeguards or hard stops.

The evaluator returns the selected mode, approval requirement, resolved context, matched rules, triggered hard stops, and human-readable reasons. Decisions are recordable for provenance.

## Security and trust properties
- The evaluator is deterministic and does not ask an LLM to authorise its own actions.
- Unknown or missing context never satisfies a permissive risk threshold.
- Capability approval requirements and policy hard stops cannot be overridden by a less cautious requested mode.
- This evaluator makes a decision only; it does not execute capabilities or grant permissions itself.
- The execution service must enforce the returned approval requirement before performing the action.
- Capability declarations are trusted only when resolved from the canonical versioned registry.

## Initial capability profiles
The initial vector buffer and reprojection capabilities are local, bounded, reversible operations. Raster window extraction performs bounded external reads and declares external access. These profiles are conservative starting metadata, not universal claims about all future uses; request context can escalate them.

## Consequences
Capability contracts now have an optional autonomy profile. The first evaluator is available as a pure function and is covered by unit tests. Product planning and Run orchestration must next consume its decision output and enforce approvals at the execution boundary.

## Non-goals
This ADR does not implement identity, consent capture, a permission service, billing approval, or a production policy administration interface. It does not claim that a policy evaluation alone authorises an operation.
