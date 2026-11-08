# ADR-002: Geo-Cell is a computation declaration only

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The Geo-Cell name is retained from earlier Foundry work, but its responsibility must be narrow enough to remain stable as the platform grows.

## Decision

A Geo-Cell is a declarative, versioned, portable instance of a computation. It references one exact capability version, exact input artifact versions, normalized parameters, output port contracts, and validation requirements.

A Geo-Cell MUST NOT contain data bytes or mutable output data; implementation code or engine-specific runtime selection; execution status, logs, timestamps, or retry state; machine-local filesystem paths; or unresolved moving references such as latest artifact aliases.

## Consequences

Cells can be validated, reviewed, shared, and versioned without execution. Execution history belongs to Runs; produced data belongs to Artifacts; executable realizations belong to capability implementations.

## Alternatives considered

- Universal data/computation object: rejected.
- Cell containing its own output and execution state: rejected because failed attempts and multiple outputs become ambiguous.
