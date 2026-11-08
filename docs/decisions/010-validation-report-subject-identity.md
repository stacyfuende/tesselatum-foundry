# ADR-010: Validation Report subjects use the identity model of the subject

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Most Foundry domain objects are versioned declarations or data snapshots. A Run is different: it is an execution attempt with a unique run ID and lifecycle, not a versioned declaration. Requiring every Validation Report subject to have a version would incorrectly impose version semantics on Runs.

## Decision

A Validation Report subject identifies:
- Artifact, Capability, Geo-Cell, Recipe, and Capability Implementation by kind, ID, and exact version; or
- Run by kind and unique run ID, without a version field.

The Validation Report schema enforces these two shapes.

## Consequences

- Validation evidence points to the correct immutable identity.
- Run history is not confused with declaration version history.
- Validators and report consumers must branch on subject kind when resolving the subject.

## Alternatives considered

- Require a version field for every subject: rejected because Runs are attempts, not versioned declarations.
- Use a synthetic Run version: rejected because it would invent a lifecycle concept and obscure the run ID.
