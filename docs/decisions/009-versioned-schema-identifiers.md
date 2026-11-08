# ADR-009: Stable versioned schema identifiers

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

JSON Schema references must resolve consistently in local development, CI, and future consumers. Relative filesystem-only references are fragile when schemas are packaged, copied, or consumed outside the repository.

## Decision

Every canonical schema receives a stable, versioned URN identifier in the namespace urn:tessellatum-foundry:schema. Shared definitions are referenced by their absolute URN. The first contract version is 1.0.0.

A breaking change to a schema's accepted structure or meaning requires a new schema version and an explicit compatibility decision. Schema files remain the canonical source; consumers resolve the URNs through an explicit local schema registry rather than relying on network retrieval.

## Consequences

- Schema references are independent of filesystem layout.
- CI can load all schemas into a deterministic local registry.
- Schema versions become explicit contract identifiers.
- Consumers must register the canonical schema resources they need.

## Alternatives considered

- Relative file references: rejected as fragile across packaging and external consumers.
- Live network-hosted schema URLs: rejected because validation should not depend on network availability.
- Unversioned identifiers: rejected because they make compatibility and migration ambiguous.
