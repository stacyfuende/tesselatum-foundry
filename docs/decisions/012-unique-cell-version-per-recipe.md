# ADR-012: A Recipe contains each Geo-Cell version at most once

- **Status:** Accepted for v0.1
- **Date:** 2026-11-08

## Context

Geo-Cell input bindings identify upstream computations by exact cell ID and version. Recipe edges identify dependencies by node ID and ports. If the same cell version appeared as multiple nodes in one Recipe, a cell-output binding would not identify which node instance it meant.

## Decision

A Recipe MUST contain a given Geo-Cell ID/version at most once. A single node may have multiple downstream edges, so fan-out and reuse of one computed output remain supported.

If a logically distinct computation needs different inputs or parameters, it must be represented by a distinct Geo-Cell declaration (and therefore a distinct cell identity or version).

## Consequences

- Cell-output bindings resolve unambiguously to one Recipe node.
- The semantic validator can cross-check cell bindings against explicit Recipe edges.
- One computed result can feed multiple downstream nodes.
- The same exact computation declaration cannot be duplicated as two separate nodes in one Recipe.

## Alternatives considered

- Bind upstream outputs by Recipe node ID inside the Geo-Cell: rejected because it would make a cell declaration depend on a particular Recipe's local node naming.
- Allow duplicate cell references and infer the source node: rejected because the binding would become ambiguous.
