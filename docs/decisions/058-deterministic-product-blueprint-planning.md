# ADR-058: Deterministic Spatial Product Blueprint Planning

- Status: Proposed for review on PR #24
- Date: 2026-11-27

## Context

Foundry needs a deterministic bridge between an outcome-oriented Spatial Product Blueprint and registered execution machinery. A blueprint describes the customer outcome, evidence requirements, reasoning nodes, deliverables, acceptance checks, and operational limits. It must not be interpreted as permission to execute arbitrary model-generated code or as proof that every requested operation exists.

## Decision

The Product Blueprint Planner compiles a validated blueprint into a deterministic, non-executing plan.

The planner:

1. Validates the blueprint and autonomy policy against versioned schemas.
2. Resolves exact, pinned Capability versions from the canonical Capability Registry.
3. Checks required input ports, parameter schemas, evidence bindings, output ports, data-kind compatibility, dependencies, and cycles.
4. Produces a deterministic topological node order.
5. Reports missing capabilities and required evidence without inventing replacements.
6. Evaluates autonomy for each resolved capability.
7. Evaluates release authorisation whenever an output declares delivery targets, regardless of a blueprint's `approval_required` flag.
8. Returns acceptance checks, resource limits, and a stable plan fingerprint derived from the blueprint, policy, and exact resolved capability contracts.

A plan with findings or missing required evidence is blocked. A plan requiring explicit authorisation is marked `approval_required`. The planner never creates Runs, artifacts, deployments, or publications.

Input binding conventions are deliberately small: `node_id.output_port` binds a reasoning node; `evidence:reference_id` names a supplied evidence reference; other strings represent externally supplied input handles.

## Trust boundary

- Only exact, canonical, versioned capability contracts may be planned.
- Delivery targets trigger the external-publication policy check; a blueprint flag cannot suppress that check.
- The fingerprint identifies planning inputs. It is not a signature, authorisation token, or guarantee that external sources remain unchanged.
- The future Run service must independently enforce approval, actor permissions, and resource limits before execution.
- Product-specific acceptance checks must pass before release.

## Consequences

Product requests can now be assessed against actual registered machinery before execution. Plans can be inspected and compared reproducibly. Missing capabilities and evidence remain visible rather than being silently substituted.

The next integration step is to make execution consume this plan, enforce approval at the Run boundary, resolve evidence into immutable inputs, and evaluate product acceptance before release.

## Non-goals

This decision does not implement Run orchestration, identity or consent capture, approval storage, source-rights verification, a cartographic renderer, product hosting, or publication. A planned blueprint is not yet a functioning customer product.
