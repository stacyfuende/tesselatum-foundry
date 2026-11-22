# Spatial information core: initial data model

**Status:** Initial implementation contract for Foundry 0.1  
**Migration:** `db/migrations/0001_spatial_information_core.sql`

## Purpose

This model adds persistent geographic information alongside, not inside, the existing computation stores. It does not alter Artifact, Geo-Cell, Recipe, Run, or Validation Report schemas.

## Identity boundaries

| Record | What its ID identifies | What it does not identify |
|---|---|---|
| Entity | A persistent real-world or modeled thing | A provider's row, a geometry hash, or a file |
| Source dataset | A registered upstream dataset/provider feed | A particular downloaded state |
| Source snapshot | One captured/retrieved state of a dataset | The current canonical truth |
| Source record | One record as supplied in one snapshot | The entity itself |
| Entity-source link | A proposed or accepted mapping between an entity and a source record | Proof that the match is correct |
| Observation | One assertion about an entity | An authoritative timeless fact |
| Representation | One versioned spatial depiction of an entity | Entity identity |
| Relationship | One directed, typed connection between entities | A mere geometric intersection |

UUIDs are internal identifiers. Provider IDs remain source keys and are scoped to a source snapshot. The same source record can be linked to more than one entity when an explicit split or interpretation requires it. One entity can be linked to records from many providers and snapshots.

## Temporal semantics

- `observed_at`: when the source or observer says the observation was made.
- `valid_time`: the interval in the represented world for which the assertion/relationship/representation applies.
- `recorded_at`: when Foundry recorded the record.

The model therefore preserves the distinction between valid time and transaction/record time. Null valid time means unknown or not supplied; it must not be interpreted as timeless.

## Initial tables

- `foundry.entity`: stable identity and broad type, initially including RoadSegment, Junction, and RoadNetwork.
- `foundry.source_dataset`: registered source identity and descriptive/rights declarations.
- `foundry.source_snapshot`: immutable capture metadata and optional content checksum.
- `foundry.source_record`: source-native key, source layer/order, and preserved JSON payload for a record.
- `foundry.entity_source_link`: explicit source-to-entity crosswalk with state, method, confidence, and decision provenance.
- `foundry.observation`: assertion about an entity, optionally tied to a source record, with observed/valid/recorded time and supersession.
- `foundry.entity_representation`: versioned geometry and attributes, linked to an observation where available.
- `foundry.entity_relationship`: directed typed relationship, optionally grounded in an observation and valid-time interval.

PostGIS geometry is stored without a fixed SRID typmod so one database can represent multiple coordinate reference systems. Every geometry must have a positive SRID. Clients must inspect the SRID and transform explicitly; no implicit reprojection occurs in storage. Geometry is indexed with GiST.

## Road-network vocabulary

The initial entity types are application-level values, not a database enum, so new domains can be introduced without an enum migration. The first road-network relationship vocabulary should include:

- `connects_to`: a road segment is incident to a junction (direction is represented by subject/object conventions or a later explicit role model).
- `member_of`: a road segment or junction belongs to a road network.
- `precedes`: directed traversal order where the source data supports it.
- `supersedes`: an explicit domain-level identity succession, distinct from a representation version replacing an earlier representation.

The first ingestion adapter must document its endpoint/topology conventions. Spatial proximity alone is not proof of network connectivity.

## Split and merge handling

A source record changing shape does not automatically create a new entity. The reconciliation process must decide whether the real-world identity persisted, changed, split, or merged.

- A geometry/attribute correction to the same represented road segment creates a new representation version and a new observation.
- A source feature split into multiple real-world entities creates multiple Foundry entities and explicit source links; the original source record remains preserved.
- Multiple source records describing one road segment may link to one entity, with disagreements retained as separate observations.
- If one entity is retired or replaced by multiple entities, record explicit typed succession relationships and lifecycle state. Do not rewrite historical identifiers or geometry.

Automated matching may propose links, but ambiguous identity decisions require a recorded policy or human review.

## Immutability and enforcement

The intended lifecycle is append-only for source snapshots, source records, observations, representations, and relationships. The initial SQL establishes foreign keys and version keys, but application-level append-only behavior and database-role enforcement are follow-on hardening. Do not claim the initial migration alone prevents a privileged database user from updating or deleting rows.

Entity lifecycle state and proposed/accepted source links are controlled state, not evidence that source history may be overwritten. Any future mutation policy must preserve an audit trail.

## Deliberate limitations

This first migration does not yet provide:
- a complete source-file/object-store lifecycle;
- a production identity-resolution algorithm;
- universal entity typing or an ontology registry;
- topology rules for every road data model;
- authenticated multi-tenant authorization;
- automated bitemporal conflict resolution;
- a production migration runner or backup/restore automation.

These are separate milestones. The migration is a first persistent information model, not a claim of production readiness.

## Applying locally

Use a disposable PostgreSQL database with PostGIS enabled:

```bash
psql "$FOUNDRY_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/migrations/0001_spatial_information_core.sql
```

The migration creates the `foundry` schema and its tables. It does not seed data or alter existing Foundry JSON/filesystem stores. Confirm PostGIS is available and the database role is allowed to install the extension before applying it to a managed database.
