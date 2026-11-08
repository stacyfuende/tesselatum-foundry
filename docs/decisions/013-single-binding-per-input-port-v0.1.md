# ADR-013: One binding per named input port in v0.1

- **Status:** Accepted for v0.1
- **Date:** 2026-11-08

## Context

A capability input may need one or multiple data objects. The initial capability set can express its required inputs through distinct named ports: for example, spatial join has left and right inputs, and zonal statistics has raster and zones inputs. Supporting arbitrary collections on one port would add binding and run-resolution complexity before the first workflows require it.

## Decision

In v0.1, each named capability input port accepts exactly one binding. A capability requiring two different inputs declares two named ports. Collection-valued ports and variadic inputs are deferred.

## Consequences

- Geo-Cell input bindings remain a simple port-to-binding object.
- Recipe edges map one source output to one target input port.
- Initial spatial join and raster zonal-statistics capabilities remain expressible with distinct named ports.
- Future collection/variadic input support requires a versioned schema change and explicit execution semantics.

## Alternatives considered

- Support arrays of bindings on every input port from the beginning: deferred because the initial capability set does not require it.
- Model all multi-input operations as a single list port: rejected because distinct semantic roles (left/right, raster/zones) should remain explicit.
