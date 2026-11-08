# ADR-028: Provide a dependency-free read-only Recipe DAG viewer

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

ADR-003 establishes the serialized Recipe contract as canonical and calls for a minimal read-only DAG viewer in v0.1. Foundry now has versioned Recipe definitions and sequential execution, but there is no way to inspect a Recipe graph visually without reading its JSON.

A viewer should make the graph legible without creating another workflow model, adding an editor, or making execution depend on a browser application.

## Decision

1. Provide a static, dependency-free HTML viewer under `viewer/`.
2. Accept the canonical Recipe JSON document through a local file selection or paste operation.
3. Render exact node IDs, exact Cell ID/version references, directed port edges, and declared Recipe outputs.
4. Compute a deterministic topological-depth layout for display only. The viewer does not modify the Recipe or persist a derived graph.
5. Report cycles and structurally unusable edges rather than presenting them as a valid DAG.
6. Keep schema validation, reference resolution, and full semantic graph validation in the Foundry control plane. The viewer is a projection, not a validator or execution client.
7. Do not require a frontend build system, network service, external JavaScript dependency, authentication, or editable graph state for this first viewer.

## Consequences

A reviewer can inspect a Recipe by opening one static HTML file and loading its canonical JSON. The viewer can be hosted independently or replaced without changing Foundry's domain model. It does not yet display live Run state, spatial extents, Artifact previews, or execution diagnostics.

## Alternatives considered

- **Build a full visual workflow editor:** rejected as premature and inconsistent with the read-only v0.1 boundary.
- **Create a separate UI graph serialization:** rejected because the canonical Recipe contract must remain the only workflow representation.
- **Make the viewer a required part of the execution service:** rejected because computation must remain usable through the API/SDK without a browser.
- **Introduce a frontend framework and build pipeline:** deferred; the initial viewer needs only a small static projection.
