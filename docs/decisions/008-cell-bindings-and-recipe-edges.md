# ADR-008: Cell input bindings and explicit Recipe edges

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

A computation graph must express dependencies between cells while each Geo-Cell remains an independently identifiable declaration. Inputs can originate from immutable data artifacts or from the output of an upstream computation. The graph also needs an explicit edge representation for validation, scheduling, and visualization.

## Decision

A Geo-Cell input binding may reference either:
- an exact immutable Artifact ID and version; or
- an exact upstream Geo-Cell ID/version and named output port.

A Recipe explicitly lists each cell-to-cell dependency as a typed edge connecting a source node/output port to a target node/input port. The two representations MUST agree. Semantic validation rejects missing, duplicate, dangling, or contradictory edges/bindings.

When a Recipe executes, each upstream output is resolved to the immutable Artifact version produced by the upstream Run. The downstream Run records that resolved artifact ID, version, and checksum.

## Consequences

- Cells remain declarative and composable.
- The Recipe graph is explicit and easy to inspect or render.
- The validator must cross-check cell bindings against Recipe edges.
- A Run must record resolved artifact snapshots, not only symbolic graph references.
- A cell-output binding is not itself an Artifact version.

## Alternatives considered

- Store dependencies only as Recipe edges: rejected because a cell's declared input binding would be incomplete outside the graph.
- Store dependencies only inside cells: rejected because the Recipe graph would have to be reconstructed for every viewer, scheduler, and graph-level validator.
- Bind downstream cells to future artifact IDs before upstream execution: rejected because it invents identities for outputs that do not yet exist.
