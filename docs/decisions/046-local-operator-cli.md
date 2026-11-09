# ADR-046: Provide a local operator CLI over the canonical SDK

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Foundry has a usable local Python SDK and a sequential Recipe execution core, but routine operator workflows require callers to write Python glue. This creates friction for evaluating the system and makes basic workspace operations difficult to reproduce from a terminal.

A launch-oriented interface should expose the existing canonical model rather than introduce a second representation of Artifacts, Cells, Recipes, Runs, or Validation Reports.

## Decision

1. Add an installed `foundry` command backed by the existing `LocalFoundry` composition root.
2. Support workspace initialization, immutable Artifact ingest and inspection, checksum-verified Artifact export, Cell and Recipe registration, Recipe execution, Run and Validation Report inspection, and canonical registry listing.
3. Accept canonical JSON documents and metadata files; do not invent a CLI-specific workflow schema.
4. Emit machine-readable JSON for successful operations and concise errors with non-zero exit status for failures.
5. Keep worker image lifecycle explicit: the CLI does not silently build, pull, or upgrade Docker images.
6. Describe the CLI as a local single-user operator interface, not a hosted API or multi-tenant security boundary.
7. Retain the implementation conformance gate and all existing validation behavior. A CLI path must not bypass canonical schemas, graph/spatial preconditions, output critics, immutable stores, or checksum verification.

## Consequences

- Developers and operators can exercise the existing local product path without writing a custom Python script.
- Artifact bytes can be ingested and exported through the same immutable checksum-verified store used by execution.
- Recipe execution returns a compact summary while detailed Run and Validation Report evidence remains inspectable.
- The local filesystem repositories remain unsuitable for concurrent multi-process or multi-tenant hosting. A separate authenticated control plane and database-backed persistence are required for a hosted launch.

## Verification status

The CLI, package entry point, operator guide, and source-level tests are committed on the isolated working branch. Project pytest, Ruff, Docker execution, and CI have not been run in this environment. This decision does not declare the CLI or any raster implementation production-ready.
