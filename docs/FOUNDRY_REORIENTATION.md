# Foundry reorientation: spatial information infrastructure

**Status:** Proposed architectural direction for Foundry 0.1  
**Date:** 2026-11-22  
**Supersedes:** The assumption that Foundry's primary purpose is a general spatial-computation engine. Existing computation work is retained as a subsystem unless a later decision demonstrates that a component should be replaced.

## 1. Decision

Tessellatum Foundry is to become the engineering foundation for **unified infrastructure for spatial data**.

Its primary responsibility is to make spatial information persistently identifiable, structured, versioned, connected, traceable, queryable, and usable by software.

Foundry must support the lifecycle of spatial information:

1. Acquire source material and record where it came from.
2. Preserve source material without silently overwriting it.
3. Identify real-world or modeled geographic entities.
4. Represent observations and assertions about those entities.
5. Maintain versioned geometries, attributes, and relationships.
6. Record temporal validity and the time at which information entered the system.
7. Expose validated spatial information through stable interfaces.
8. Apply spatial computations to information and preserve the lineage of resulting outputs.
9. Allow applications, analysts, and eventually agents to use the same governed foundation.

Foundry is not defined by a particular GIS engine, file format, database vendor, user interface, or AI model.

## 2. The key architectural correction

A computation engine is necessary, but it is not the whole infrastructure.

The current repository is strongest in declarative computation: Capabilities, Geo-Cells, Recipes, Runs, Artifacts, conformance, execution isolation, and validation evidence. Those components are useful and should not be discarded merely because the primary product responsibility is being clarified.

However, a spatial information platform must distinguish at least these concepts:

| Concept | Meaning | Identity/lifecycle |
|---|---|---|
| Geographic entity | The thing being represented: road segment, junction, building, parcel, place, network, or modeled object | Stable identity across source changes where identity can be established |
| Observation | A source-backed assertion about an entity at a time or over an interval | Independently identified, attributable, time-qualified, and revisable by supersession—not silent mutation |
| Representation | A particular geometry, attribute state, or structured depiction of an entity | Versioned; may vary by source, scale, purpose, or time |
| Source record | What an upstream dataset or provider actually supplied | Preserved with source identity, retrieval context, and provenance |
| Artifact | An immutable data payload or file used, produced, or exchanged by the system | Content/version identity and checksum |
| Computation | A declared operation applied to explicit inputs | Capability and implementation versions |
| Run | One execution attempt with resolved inputs and recorded outputs | Append-only execution history |
| Relationship | A typed connection between entities or records | Versioned or time-qualified where its meaning changes |
| Validation evidence | A record of what was checked and what was found | Bound to the exact subject and version assessed |

These concepts must not be collapsed into one universal Cell, Feature, or Artifact record.

In particular:
- An Artifact is not a geographic entity.
- A geometry is not the identity of the entity it depicts.
- An observation is not necessarily the current truth.
- A source identifier is not automatically a durable Foundry identifier.
- A successful computation does not establish that its inputs are authoritative or its result is suitable for every purpose.

## 3. Foundry's architectural layers

### 3.1 Spatial information core

Owns canonical identity and the persistent information model:

- entity identity and entity types;
- versioned entity state and representations;
- source records and source-to-entity mappings;
- observations and assertions;
- typed entity relationships;
- spatial and temporal metadata;
- provenance and lineage;
- validation state and evidence references.

This is the foundational layer. It must remain useful even when no computation is running.

### 3.2 Ingestion and reconciliation

Responsible for bringing external and user-supplied information into the core without destroying source meaning:

- source registration and dataset snapshots;
- adapters and import jobs;
- format and schema validation;
- coordinate reference and dimensionality checks;
- normalization that preserves original values;
- entity matching and identity resolution;
- conflict handling and review queues;
- explicit acceptance, rejection, or supersession of observations.

Ingestion must preserve raw inputs and record transformations. It must not silently convert a source claim into canonical truth.

### 3.3 Spatial query and service layer

Provides stable ways to retrieve and inspect information:

- entity lookup and source crosswalks;
- geometry and attribute retrieval by version or time;
- spatial predicates and bounded spatial search;
- relationship traversal;
- provenance and history inspection;
- filtered exports and interoperable representations.

The first service boundary can be a single API backed by one managed PostgreSQL/PostGIS database. Distributed services are not a starting requirement.

### 3.4 Computation and transformation layer

This is where the repository's existing engineering belongs.

Retain and evolve the existing:
- Artifact model;
- Capability contracts and conformance suites;
- Geo-Cell declarations;
- Recipe graphs;
- Run lifecycle and immutable lineage;
- independent validation reports;
- replaceable Shapely/PostGIS and other workers;
- local SDK and execution isolation.

The computation layer consumes explicit source or canonical information snapshots and produces new versioned outputs. It must never silently mutate canonical entity history.

The existing computation contracts should be integrated through adapters and explicit references, not forced to become the identity model for all spatial information.

### 3.5 Application and agent interfaces

Applications, services, notebooks, and agents use Foundry through the same explicit contracts and service boundaries.

Natural-language planning and autonomous agents are optional clients. They must not become trusted sources of truth or bypass validation, authorization, provenance, or human review gates.

## 4. Initial bounded domain: road networks

Foundry 0.1 should prove the information model on one useful, understandable domain: **road-network information**.

The first implementation should be deliberately bounded to a defined study area and a declared source set. It should not attempt to build a universal global geographic database.

Initial entity types:
- RoadSegment
- Junction
- RoadNetwork

Initial capabilities:
- preserve imported source records;
- assign durable Foundry entity IDs;
- maintain source identifier crosswalks;
- store versioned road geometries and selected attributes;
- represent segment-to-junction and network membership relationships;
- retain observations from multiple sources without overwriting conflicts;
- query by ID, bounding box, and spatial relationship;
- inspect entity history and provenance;
- export a reproducible snapshot.

The first domain model should explicitly address split/merge identity changes, source ID changes, geometry edits, one-way/direction attributes, network connectivity, and temporal changes. It must not assume that a road segment's identity is equivalent to a row ID or a geometry hash.

The study area and initial sources are to be selected after inspecting the available source data and the existing Spatial Methods repository. The system must not hardcode a particular city or provider into its foundational abstractions.

## 5. Persistence and deployment posture

The initial production-shaped architecture should remain small:

- **GitHub:** source code, schemas, migrations, tests, documentation, CI, review, and release history.
- **PostgreSQL/PostGIS:** canonical structured spatial information and transactional metadata.
- **Object storage:** immutable source files, large artifacts, exports, and content-addressed payloads where appropriate.
- **One API service:** authenticated access to the core model and query operations.
- **Background worker process:** ingestion and computation jobs that need asynchronous execution.

Local development may use Docker Compose. A managed Postgres/PostGIS service and modest object storage can be introduced when the first end-to-end slice is ready. Do not provision a fleet of services, Kubernetes, a global event bus, or a distributed database for 0.1.

Database migrations, backup/restore, access control, retention, and storage lifecycle must be designed before real customer data is treated as safely persisted.

## 6. Data and identity principles

1. **Stable internal identity:** Foundry IDs identify Foundry entities, not source rows or geometry encodings.
2. **Source fidelity:** preserve original source records or immutable source snapshots and their identifiers.
3. **No silent overwrite:** new information creates a new observation or version with explicit provenance.
4. **Temporal clarity:** distinguish when a fact is valid in the represented world from when Foundry learned or recorded it. Adopt bitemporal fields where the domain requires them; do not pretend one timestamp answers both questions.
5. **Multiple representations:** an entity may have different geometries or representations by source, scale, purpose, or time.
6. **Explicit uncertainty:** identity matches, positional accuracy, completeness, and source authority are not assumed.
7. **Typed relationships:** relationships have defined semantics and direction; topology is not inferred solely from visual proximity.
8. **Reproducible computation:** every derived result points to exact input versions, capability and implementation versions, parameters, and execution evidence.
9. **Rights-aware use:** provenance records are not legal authorization. Policy decisions must be explicit and evidence-based.
10. **Human-authored truth remains intact:** AI may assist with interpretation or proposals, but cannot silently replace original human or source information.

## 7. What Foundry is not

Foundry 0.1 is not:
- a new desktop GIS;
- a universal global map or complete digital twin;
- a replacement for every upstream authoritative data provider;
- a general-purpose arbitrary-code execution service;
- a marketplace or social network;
- an autonomous AI geographer;
- a collection of unrelated microservices;
- a requirement that every Tessellatum product use every Foundry capability.

## 8. First end-to-end milestone

The first milestone is not "support every spatial data type." It is a working, testable road-network information slice:

1. Define the minimum entity, source-record, observation, representation, relationship, and provenance schemas.
2. Create PostgreSQL/PostGIS migrations and integrity constraints.
3. Import one bounded road dataset while preserving its source identity and snapshot.
4. Assign Foundry IDs and create explicit source crosswalks.
5. Store versioned geometries and attributes.
6. Represent network connectivity and validate topology with declared tolerances/rules.
7. Expose read APIs for entity lookup, spatial query, provenance, and history.
8. Export a deterministic snapshot.
9. Demonstrate a computation using the existing Capability/Recipe/Run subsystem and trace its output back to exact source and entity versions.
10. Test ingestion repeatability, updates, source conflicts, identity changes, temporal queries, and backup/restore.

A milestone is complete only when the data survives process restarts, can be queried through the service boundary, retains its provenance, and can be independently tested. A schema document or in-memory demo is not sufficient.

## 9. Relationship to Spatial Methods

Spatial Methods remains the knowledge and methods foundation: concepts, mathematical foundations, algorithms, data acquisition methods, implementation references, and tested recipes.

Foundry is the operational information and computation infrastructure that applies, stores, connects, and serves spatial information.

The boundary is complementary:
- Spatial Methods explains and develops methods.
- Foundry manages persistent spatial information and executes governed computations.
- Applications use the resulting services to solve customer problems.

Foundry may reference Spatial Methods records and implementations, but it must not duplicate the repository's entire knowledge catalogue or turn itself into a second methods encyclopedia.

## 10. Reorientation policy

This document establishes a proposed direction, not permission to disregard evidence or break working behavior casually.

Before replacing existing components:
- inspect their code, tests, interfaces, and consumers;
- identify whether they can serve as the computation layer;
- preserve useful contracts and historical provenance;
- write a superseding ADR for any accepted decision whose meaning changes;
- make changes on a dedicated branch;
- keep the main branch stable until the new foundation is reviewed and verified.

The old concept is not sacred. The working software is valuable only insofar as it serves the new purpose.
