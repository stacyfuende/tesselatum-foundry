# ADR-058: Deterministic Spatial Product Blueprint Planning

- Status: Accepted
- Date: 2026-11-27

## Context

Foundry needs a bridge between an outcome-oriented Spatial Product Blueprint and the existing registered execution machinery. A blueprint describes the customer outcome, evidence requirements, reasoning nodes, deliverables, acceptance checks, and operational limits. It must not be interpreted as permission to execute arbitrary model-generated code or as proof that every requested operation exists.

## Decision

Introduce a deterministic, non-executing Product Blueprint Planner.

The planner:

1. Validates the blueprint and autonomy policy against the repository's versioned JSON Schemas.
2. Resolves every reasoning node to an exact, pinned Capability version in the canonical Capability Registry.
3. Checks declared input ports, required bindings, parameter schemas, dependency references, output ports, and compatible data kinds.
4. Derives a stable topological node order and rejects dependency cycles.
5. Reports required evidence that has not been supplied.
6. Evaluates autonomy for each resolved capability and for explicitly approval-gated publication outputs.
7. Returns a structured plan, missing-capability/evidence lists, and actionable findings.

Input binding conventions are deliberately small: `node_id.output_port` binds a prior reasoning node; `evidence:reference_id` names a supplied evidence reference; other strings represent externally supplied input handles.

A missing or unpinned capability is a blocking finding. The planner never substitutes a similar operation, invents a method, generates executable code, creates Runs, writes artifacts, deploys applications, or publishes products.

## Consequences

- Product requests can be assessed against actual registered machinery before execution.
- The planner is deterministic and testable without contacting external services.
- A plan is not an authorization token. The eventual execution boundary must independently enforce approval, resource limits, actor identity, and exact capability/implementation resolution.
- Evidence role matching is currently a presence check; richer source-quality, rights, freshness, and provenance validation remains a later stage.
- The current planner does not yet synthesize missing capabilities or translate every output experience into a deployable frontend. It exposes gaps rather than hiding them.
