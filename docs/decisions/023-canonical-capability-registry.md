# ADR-023: Resolve execution against canonical Capability contracts

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The Run service previously accepted a Capability object from its caller and checked only its schema and ID/version reference. A caller could therefore supply altered parameter limits, input/output port constraints, or measurement semantics while retaining the same Capability ID and version. That would make the implementation conformance manifest appear to certify semantics different from the ones actually executed.

## Decision

1. Maintain canonical, immutable Capability versions under `capabilities/<capability_id>/<version>.json`.
2. Validate every registered Capability against `capability.schema.json` when the registry loads.
3. Resolve a Capability by its exact ID and version and require the supplied object to equal the canonical registered object before execution.
4. Apply the exact-canonical check to every node in a Recipe before the first node is dispatched. Do not allow a later altered contract to cause a partially executed Recipe.
5. Package canonical Capability contracts with schemas and implementation manifests under `share/tessellatum-foundry/`.
6. Keep Capability semantics separate from engine-specific implementation manifests. An implementation's conformance status applies to the exact registered Capability version, not to caller-supplied lookalike objects.

## Consequences

The current vector.buffer Run service can no longer execute a modified contract under the existing `vector.buffer@1.0.0` identity. A semantic change requires a new registered Capability version and corresponding implementation conformance evidence. Recipe execution performs this check for all referenced nodes before scheduling.

The registry is local and repository-backed. It is not yet a distributed, signed, tenant-aware contract registry.

## Alternatives considered

- **Trust caller-supplied Capability JSON after schema validation:** rejected because schema validity does not establish canonical identity.
- **Compare only ID and version:** rejected because the same identifiers can accompany altered semantics.
- **Embed engine implementation details into the Capability:** rejected because Capability semantics and implementation identities have independent versioning and conformance lifecycles.
