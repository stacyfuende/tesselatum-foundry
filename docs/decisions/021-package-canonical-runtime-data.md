# ADR-021: Package canonical schemas and implementation manifests

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The Run service and implementation registry depend on canonical JSON Schemas and versioned implementation manifests. Resolving those files relative to the source checkout works during repository development but fails when Foundry is installed as a wheel in a different environment. These contracts are runtime dependencies, not development-only repository documentation.

## Decision

1. Keep the repository `schema/` and `implementations/` directories as the canonical authoring locations.
2. Package all canonical schema JSON files and the registered vector.buffer implementation manifests as distribution data under `share/tessellatum-foundry/`.
3. Resolve these data directories from the source checkout when present; otherwise resolve them from the Python installation's data prefix.
4. Add a CI smoke test that installs a non-editable distribution into an isolated virtual environment and resolves all schemas and both conformant implementation manifests without relying on the source checkout.
5. Do not duplicate schema or manifest contents inside Python modules. The repository files remain the single source of truth.

## Consequences

The package can locate its canonical validation contracts and implementation registry when installed outside the repository. The initial distribution contains the schemas and the two vector.buffer manifests. Future capability manifests must be added to the package-data configuration and the installed-distribution smoke test.

## Alternatives considered

- **Resolve files only relative to the repository root:** rejected because installed wheels do not contain the repository layout.
- **Duplicate JSON files inside Python package resources:** rejected because duplicated contracts can drift from the canonical repository files.
- **Embed schema and manifest JSON as Python constants:** rejected because it obscures the canonical source and makes review/versioning less transparent.
