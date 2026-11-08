# Tessellatum Foundry

Tessellatum Foundry is being developed as infrastructure for describing, composing, executing, validating, and reproducing spatial computations across compatible engines and execution environments.

The repository is intentionally being established from architectural contracts before implementation. The first milestone is a dependable, auditable spatial computation system—not a general-purpose GIS application and not an AI demo.

## Current status

- [x] Repository established.
- [x] Initial architectural decisions documented.
- [x] Core domain contracts drafted as JSON Schema.
- [x] v0.1 acceptance criteria documented.
- [x] Initial JSON Schema validator and Recipe graph semantic validator implemented with CI tests.
- [x] Initial spatial metadata and pre-execution CRS/unit validator implemented with tests.
- [ ] Methodological, rights, and execution/output validators implemented.
- [ ] Deterministic local execution path implemented.
- [ ] Remote worker path implemented and conformance-tested.
- [ ] Initial vector and raster capabilities implemented.
- [ ] Read-only recipe graph viewer implemented.

Items are marked complete only when the repository contains implementation and tests demonstrating them.

## Start here

1. [Architecture](ARCHITECTURE.md)
2. [Decision register](docs/decisions/README.md)
3. [Schemas](schema/)
4. [v0.1 acceptance criteria](tests/acceptance/README.md)

## Foundational model

1. **Artifact** — a versioned data object.
2. **Capability** — a versioned contract describing an operation.
3. **Geo-Cell** — a declarative, versioned instance of a computation.
4. **Run** — one attempt to execute a Geo-Cell.
5. **Recipe** — a versioned graph composing Geo-Cells.

The Validation Report is a separate evidence object. Implementations are registered separately from capability contracts.

## Development principles

- Contracts precede implementations.
- A schema-valid object is not necessarily semantically valid.
- Execution is deterministic where the capability permits it and always auditable.
- Every run records the exact versions and inputs it used.
- Workers are replaceable, but must conform to a shared execution contract.
- Capability implementations must pass conformance tests before being treated as interchangeable.
- The planner is optional and never required by the execution core.
- Security, provenance, licensing, and cost visibility are architectural concerns.

## Scope boundary

This repository is Tessellatum Foundry. It is an independent project with its own architecture, implementation, and lifecycle.
