# ADR-005: Capability contracts are independent of implementations

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry should support multiple spatial engines without making engine-specific details part of the public meaning of an operation.

## Decision

A Capability defines operation semantics, typed inputs, parameters, outputs, preconditions, and validation expectations. Implementations are separately registered realizations of a specific capability version.

An implementation is not interchangeable merely because it uses the same capability name. It must pass a conformance suite covering the semantics relevant to that operation.

For v0.1, vector.buffer is the first portability proof and must have two independent implementations (initial candidates: Shapely and PostGIS) that pass the same declared conformance suite.

## Consequences

- Engine-specific implementations can evolve independently.
- Foundry records the exact implementation used by each Run.
- Capability contracts must specify details such as units, CRS handling, geometry validity, dimensionality, precision, and edge-case behaviour.
- Conformance tests need tolerances where exact byte equality is inappropriate.

## Alternatives considered

- One implementation per capability: rejected because it would not test the portability claim.
- Treat all engines as equivalent behind a common function name: rejected because it hides semantic differences.
- Automatic engine optimizer in v0.1: deferred until conformance and operational reliability are demonstrated.
