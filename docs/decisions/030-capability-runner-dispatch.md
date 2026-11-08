# ADR-030: Dispatch Recipe nodes through exact Capability runner registrations

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The Recipe orchestrator currently delegates every node to one vector.buffer Run service. This couples graph scheduling to one capability and one worker, even though Recipe nodes already reference exact, versioned Capability contracts.

Adding capabilities by extending the Recipe orchestrator with capability-specific conditionals would make the control plane increasingly dependent on individual spatial operations. It would also make worker selection and runtime identity ambiguous when a Recipe uses more than one execution backend.

## Decision

1. Define a capability-neutral CellExecutionRunner protocol at the control-plane/worker boundary. Capability-specific Run services implement this interface.
2. Register runners by the exact (capability_id, capability_version) pair. Never select a runner by capability name alone or silently substitute a compatible-looking version.
3. Resolve the runner for every Recipe node during preflight. Missing registrations, worker configuration failures, non-canonical Capability definitions, or non-conformant implementations MUST fail before the first Run is created.
4. Dispatch each node to its exact registered runner while preserving the existing immutable Run, Artifact, validation-report, and Recipe-node lineage contracts.
5. Pin runtime image identity per runner within a Recipe execution. A runtime digest discovered for one runner MUST NOT be reused for a different runner. Repeated nodes handled by the same runner retain the first pinned digest.
6. Preserve the existing single cell_runner constructor argument as a compatibility convenience. It registers that runner under the exact Capability version declared by its worker. New compositions may supply cell_runners explicitly.
7. This decision establishes orchestration extensibility; it does not claim that additional capabilities or parallel scheduling are implemented. The currently available concrete Run service remains vector.buffer@1.0.0.

## Consequences

The Recipe control plane no longer needs to know which spatial operation a node performs. It validates the graph and resolves an exact runner before scheduling. New capability-specific Run services can be introduced behind the same interface without changing graph traversal or lineage handling.

The first release remains sequential. Runtime pinning is scoped to the selected runner so a future mixed-backend Recipe can preserve each backend's own immutable runtime identity.

## Alternatives considered

- Add capability-specific branches to RecipeExecutionService: rejected because each new operation would expand orchestration logic.
- Resolve by capability ID only: rejected because capability versions can change semantics and must be selected exactly.
- Use one runtime digest for an entire Recipe: rejected because different runners may execute from different immutable runtime images.
- Introduce parallel scheduling at the same time: deferred. Capability dispatch and per-runner identity must be stable before concurrency is introduced.
