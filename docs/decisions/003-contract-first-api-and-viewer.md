# ADR-003: Canonical contracts and API with a read-only viewer

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry needs a legible way to inspect spatial computation graphs, but a visual editor could prematurely drive the domain model and consume effort before execution contracts are proven.

## Decision

The serialized contracts and API/SDK are canonical. v0.1 includes a minimal read-only Recipe DAG viewer. The viewer renders the canonical Recipe model and does not create a second workflow representation.

A full visual editor is deferred. A natural-language planner is optional and deferred from the critical path.

## Consequences

- Workflows remain expressible and testable without the viewer.
- The graph can be demonstrated to technical and nontechnical reviewers.
- The viewer can be replaced without changing the execution core.
- v0.1 must provide stable identifiers and graph semantics before viewer implementation.

## Alternatives considered

- Pure API/SDK with no visual representation: deferred, because graph legibility has demonstration and review value.
- Full visual builder first: rejected as premature.
- Natural-language agent first: rejected because it would make the core harder to verify independently.
