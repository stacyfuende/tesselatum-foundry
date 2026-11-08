# ADR-022: Execute Recipes as ordered groups of immutable cell Runs

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The current local execution service proves one Geo-Cell Run. Foundry's core composition model is a versioned Recipe DAG, and a Recipe must resolve cell-output bindings to the immutable Artifacts produced by upstream Runs. Rewriting a Geo-Cell's declared binding at execution time would falsify the exact declaration recorded by the Run.

A Recipe execution also needs a way to correlate its per-cell Runs without changing the meaning of Run: one Run remains one attempt to execute one exact Geo-Cell version.

## Decision

1. Execute Recipe nodes in deterministic topological order for the first local Recipe runner. Parallel scheduling is deferred.
2. Create one ordinary Run per executed node. Every Run retains the exact Geo-Cell and Capability references and also records the exact Recipe reference, shared `recipe_execution_id`, declared `recipe_node_id`, and deterministic topological `recipe_node_order`.
3. Keep the original Geo-Cell definition immutable. For a `cell_output` binding, the Recipe runner resolves the upstream node's successful Run output to an immutable Artifact reference and supplies that resolution separately to the single-cell Run service.
4. The Run service verifies that the referenced upstream Run succeeded, belongs to the exact upstream Geo-Cell version named by the binding, and produced the requested output port and Artifact reference. It records the resolved Artifact ID, version, checksum, source Run ID, and source output port in the downstream Run input snapshot.
5. Validate the complete Recipe graph, all cell/capability references, external Artifact references, and declared spatial relationships before starting the first node. Each cell Run then repeats its own resolved-input and spatial preflight before dispatch.
6. If a node fails, stop scheduling downstream nodes. Previously succeeded Runs and immutable output Artifacts remain intact; the Recipe execution is reported as failed and is not represented as a successful partial result.
7. The first Recipe runner is sequential and supports only capabilities with a registered, conformant local worker adapter. It does not implement parallel execution, caching, remote scheduling, or cross-tenant execution.
8. Pin the immutable runtime image ID digest established by the first node across every subsequent node in the same Recipe execution. Each Run records that same digest; a later change to a mutable image tag must not silently change the runtime halfway through a Recipe.\n9. Correlate Runs through `recipe_execution_id`; do not introduce a sixth core domain object for a Recipe-level Run in this increment. The execution service returns an aggregate result, while the per-cell Run records remain the durable execution evidence.

## Consequences

A two-node or multi-node vector.buffer Recipe can execute end to end while preserving the original Geo-Cell declarations and resolving each downstream input to a checksummed upstream Artifact. A failed downstream cell does not rewrite or roll back successful upstream Runs. Run queries can group all cell attempts from one Recipe execution through the correlation ID.

The first implementation is sequential. The aggregate result is derived by the Recipe runner; the durable source of truth remains the per-cell Runs and their correlated Recipe reference.

## Alternatives considered

- **Rewrite cell_output bindings into artifact bindings in the Geo-Cell:** rejected because the Run would no longer point to the exact immutable declaration it claims to execute.
- **Use one Run record for the whole Recipe:** rejected because Run is defined as one attempt to execute one Geo-Cell version.
- **Add a new core RecipeRun entity immediately:** deferred; a correlation ID and aggregate service result are sufficient for the first sequential runner.
- **Schedule independent nodes in parallel:** deferred until the sequential resolver and failure semantics are proven.
