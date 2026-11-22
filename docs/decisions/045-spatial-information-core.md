# ADR-045: Introduce a persistent spatial information core

- **Status:** Proposed
- **Date:** 2026-11-22
- **Decision owners:** Foundry maintainers

## Context

Foundry has established persistent filesystem stores for immutable computational Artifacts, versioned Geo-Cell/Recipe definitions, Runs, and validation reports. Those records describe computational work and its data payloads. They do not provide durable identity and history for the geographic entities represented inside those payloads.

The reoriented Foundry vision requires the system to distinguish geographic entities, source records, observations, representations, relationships, and computational Artifacts. Reusing Artifact IDs or geometry hashes as geographic identity would conflate different lifecycles and make cross-source reconciliation and temporal history unreliable.

## Decision

Introduce a separate PostgreSQL/PostGIS-backed spatial information core in the `foundry` schema.

The initial model contains:
- stable `entity` identity;
- registered `source_dataset` and immutable `source_snapshot` records;
- preserved `source_record` payloads and source-native keys;
- explicit `entity_source_link` crosswalks with review state and confidence;
- source-backed or user-authored `observation` assertions;
- versioned `entity_representation` geometries and attributes;
- typed, directed, time-qualified `entity_relationship` records.

The model distinguishes observation time, valid time, and record time. Geometry uses PostGIS with a spatial index and per-row SRID rather than a fixed database-wide CRS. Reprojection remains explicit.

The first bounded domain is road networks, initially using application-level entity types such as RoadSegment, Junction, and RoadNetwork. The database does not hard-code a closed entity-type enum.

The existing filesystem Artifact store, definition store, and Run repository remain intact. Computation will later refer to exact entity/representation/observation references through explicit metadata or a dedicated input contract; it will not mutate canonical information records.

## Consequences

- Foundry gains durable geographic identity separate from data files and computation outputs.
- Source disagreements and changing provider identifiers can be preserved rather than overwritten.
- Entity split/merge decisions can be represented explicitly.
- Spatial history and relationship queries become possible.
- PostgreSQL/PostGIS becomes a required persistence component for the information core, while local computation-only SDK use can remain available without it.
- A migration runner, database repository layer, access control, append-only enforcement, backup/restore, and production deployment are still required before production use.

## Alternatives considered

1. **Store entities inside Artifact metadata.** Rejected: artifacts are immutable payload versions and are not a relational identity/relationship model.
2. **Use source IDs as canonical IDs.** Rejected: IDs are provider-scoped and may change or be reused.
3. **Use geometry hashes as identity.** Rejected: geometry changes do not necessarily mean entity identity changes; different entities can share geometry.
4. **Use Geo-Cell as the universal object.** Rejected: Geo-Cells are computation declarations by existing accepted ADRs and must remain distinct.
5. **Build a custom spatial database or distributed graph first.** Rejected for 0.1: unnecessary operational complexity before a bounded domain is proven.

## Verification

The migration must be applied to a disposable PostgreSQL/PostGIS instance. Verification must cover table creation, foreign-key integrity, JSON constraints, geometry SRID checks, GiST index creation, duplicate source-key rejection within a snapshot, multiple source links to one entity, multiple representations per entity, and valid-time storage. Application repositories and ingestion tests are follow-on work.
