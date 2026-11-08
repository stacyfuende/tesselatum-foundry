# ADR-024: Immutable versioned storage for Geo-Cells and Recipes

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The single-cell and Recipe execution services can validate and execute supplied definitions, but accepting caller-provided dictionaries is not a durable way to manage exact Geo-Cell and Recipe versions. Execution needs a stable source from which it can resolve the declarations referenced by a Run. Capability contracts and implementation manifests already have canonical registries; user-authored Cells and Recipes need a separate lifecycle.

Artifacts are data products with spatial metadata, rights, and storage semantics. Geo-Cells and Recipes are definitions, not Artifacts, and must not be stored by pretending they are data outputs.

## Decision

1. Store Geo-Cell and Recipe definitions in a dedicated `VersionedDefinitionStore`, separate from the Artifact store.
2. Validate each Cell or Recipe against its own JSON Schema before accepting it.
3. Address definitions by exact `kind`, ID, and version. Hash the identity for the local filesystem path; never derive paths directly from caller-supplied IDs.
4. Persist a definition record containing kind, exact definition reference, creation timestamp, creator identity, canonical definition JSON, and a SHA-256 checksum covering the complete record payload.
5. Treat each kind/ID/version as immutable. Repeating the same definition by the same creator is idempotent; different content or creator provenance is rejected. A change requires a new version.
6. Validate the record and its embedded definition on every read, verify that the record identity matches its storage path, and verify its checksum before returning the definition.
7. Allow the Recipe execution service to resolve a registered Recipe, its exact Cell versions, and their canonical Capability versions through the respective registries before scheduling any node.
8. Keep the initial store filesystem-backed and local. It does not provide distributed transactions, multi-process locking, tenancy, authorization, or signed provenance.

## Consequences

Foundry can execute a Recipe by reference instead of requiring callers to assemble arbitrary dictionaries. Every Run still snapshots exact Cell, Capability, and Recipe identities. The immutable definition store gives the API/SDK layer a durable source of definitions without conflating definitions with Artifacts.

The current filesystem adapter is suitable for local development and single-process execution. A deployed control plane will need a shared transactional store and authenticated creator identity before multi-instance or multi-tenant use.

## Alternatives considered

- **Store Geo-Cells and Recipes as Artifacts:** rejected because definitions and data products have different lifecycle and validation semantics.
- **Allow in-place updates to a definition version:** rejected because existing Runs must continue to reference the exact declaration they executed.
- **Accept definitions only as request-body dictionaries:** rejected as the sole persistence model because it does not establish a durable registry or immutable identity.
- **Introduce a distributed database immediately:** deferred until the local definition and execution contracts are proven.
