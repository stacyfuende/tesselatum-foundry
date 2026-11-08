# ADR-007: JSON Schema contracts with a separate semantic validation layer

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry needs language-neutral, testable contracts. Structural schemas alone cannot validate cross-object references, graph topology, spatial compatibility, methodological suitability, or runtime output correctness.

## Decision

- JSON Schema Draft 2020-12 is the canonical structural contract format.
- JSON files in schema/ are the canonical schema sources.
- YAML may be used for human-authored instances, but those instances must validate against the same JSON Schema contracts.
- Python is the initial semantic-validation and execution implementation language.
- TypeScript client types may be generated from the canonical schemas; generated types are not independent sources of truth.
- Semantic validation is a separate, explicit pipeline covering references, graph, spatial, methodological, rights/security, and execution/output checks.

## Consequences

- Contracts can be consumed by multiple languages.
- Structural validation can run before semantic validation.
- Cross-field and cross-object invariants require tested domain validators.
- Schema changes require compatibility review and corresponding fixture/test updates.
- Schema validity must never be described as proof of spatial or methodological correctness.

## Alternatives considered

- Python classes as canonical model: rejected because it makes the contract language-dependent.
- TypeScript types as canonical model: rejected for the same reason.
- A custom DSL: deferred because it adds tooling and maintenance cost before the domain model is proven.
- JSON Schema alone: rejected because it cannot establish spatial and cross-object truths.
