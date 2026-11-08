# ADR-001: Separate the five domain concepts

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The earlier universal Geo-Cell abstraction combined data, algorithms, configured computations, execution state, and workflow composition. These entities have different identities, reuse patterns, provenance requirements, and lifecycles. Combining them makes versioning, caching, failure handling, and data reuse ambiguous.

## Decision

Foundry models five separate first-class concepts:

1. Artifact — versioned data.
2. Capability — versioned operation contract.
3. Geo-Cell — declarative computation instance.
4. Run — one execution attempt.
5. Recipe — versioned graph of computations.

Validation Reports and capability implementations are separate supporting entities.

## Consequences

- Each concept can evolve and be versioned independently.
- A failed Run does not make its Geo-Cell invalid.
- Data can be reused across computations without being owned by them.
- Recipes can be inspected and shared without being executed.
- More explicit references and schemas are required.

## Alternatives considered

- One universal Geo-Cell containing data and computation: rejected because it conflates lifecycles and creates ambiguous cache/provenance semantics.
- A generic workflow-only model: rejected because it does not give individual computation declarations an independent identity.
