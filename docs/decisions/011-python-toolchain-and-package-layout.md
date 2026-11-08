# ADR-011: Python toolchain and source package layout

- **Status:** Accepted for v0.1
- **Date:** 2026-11-08

## Context

Foundry needs an implementation language for semantic validation and the first deterministic execution components. The initial contract tests also need a repeatable local and CI environment.

## Decision

- Use Python 3.11 or newer for the initial implementation.
- Use a src-layout package named tessellatum_foundry.
- Use jsonschema Draft 2020-12 validation for structural contracts and the referencing library for explicit local schema registries.
- Use pytest for tests and Ruff for linting.
- Keep engine-specific geospatial dependencies out of the base contract-validation layer. Add them with the capability/runtime that requires them.
- CI initially runs on Python 3.11. Expand the supported Python matrix only after dependency and engine compatibility are tested.

## Consequences

- The initial domain and semantic validation code is Python-native.
- The contract format remains language-neutral.
- Heavy GIS dependencies do not burden schema-only consumers or CI.
- Python 3.11 is a conservative baseline; later versions require an explicit compatibility check.

## Alternatives considered

- TypeScript-first implementation: rejected for the initial spatial execution and validation layer.
- Install GDAL, QGIS, and database clients in the base environment: rejected because the first milestone does not need them and their platform constraints should remain isolated.
- No package structure until later: rejected because semantic validation is now a reusable domain component, not just a one-off script.
