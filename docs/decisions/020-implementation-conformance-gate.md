# ADR-020: Gate execution on registered implementation conformance

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

A worker adapter can report an implementation ID and version, but self-reported identity does not establish that the implementation is registered, targets the exact Capability version, or has passed the shared conformance suite. The Run service must not dispatch work through an implementation that is unknown or not yet certified against the Capability contract.

## Decision

1. Maintain implementation manifests separately from Capability contracts under `implementations/`. Each manifest is validated against `capability-implementation.schema.json`.
2. Resolve implementations by exact `implementation_id` and implementation `version`.
3. Before creating a Run, require the manifest to target the exact Capability ID and version supplied by the Geo-Cell.
4. Only manifests with `conformance.status = passed` are eligible for this execution path. `not_run`, `partial`, and `failed` implementations are rejected before a Run is created.
5. The worker adapter's declared implementation identity must resolve to the registered manifest. The Run records the manifest's implementation ID and version, while the runtime image ID is captured separately at execution time.
6. The initial registry is repository-backed and local. A future deployed control plane must provide an authenticated, immutable implementation registry; this local loader is not a distributed registry or a signature-verification mechanism.

## Consequences

Execution is now gated by reviewed, schema-valid implementation metadata and conformance status. A worker cannot be selected solely because it implements the Python protocol. The registry remains intentionally small and does not yet perform automatic engine selection, runtime compatibility scoring, signature verification, or remote worker discovery.

## Alternatives considered

- **Trust worker self-reported implementation identity:** rejected because it does not prove registration or conformance.
- **Allow implementations with partial or unrun conformance:** rejected for the initial deterministic execution path; an unproven backend must not be represented as interchangeable.
- **Embed implementation details in the Capability contract:** rejected because Capability semantics and engine-specific realizations have separate identities and lifecycles.
