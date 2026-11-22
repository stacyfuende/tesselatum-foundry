# Project vision

**Status:** Proposed strategic direction — Foundry spatial information infrastructure  
**Date:** 2026-11-22

## The ambition

Tessellatum's north star is **unified infrastructure for spatial data**.

Tessellatum Foundry is the engineering foundation for that ambition: a system through which spatial information can be acquired, preserved, identified, structured, versioned, connected, queried, transformed, validated, and served to applications and people.

The objective is larger than running GIS algorithms. Spatial information must remain meaningful and usable across datasets, providers, time periods, computational engines, applications, and teams. Foundry therefore needs both a persistent information foundation and a governed computation system.

## What Foundry owns

Foundry owns the operational lifecycle of spatial information and the reusable computation that acts on it.

Its responsibilities include:

- durable identity for geographic and modeled entities;
- source records, observations, assertions, and provenance;
- versioned geometries, attributes, and representations;
- typed spatial, network, and domain relationships;
- temporal history and explicit uncertainty;
- ingestion, reconciliation, and source-to-entity crosswalks;
- spatial querying, retrieval, and interoperable exports;
- versioned computational capabilities and implementations;
- reproducible workflows, execution records, and validation evidence;
- stable service interfaces for applications, analysts, and agents.

Foundry does not assume that one source is authoritative, one geometry is the entity, one observation is the truth, or one successful computation proves suitability.

## The conceptual model

The information model distinguishes:
- **Geographic entity:** the thing being represented.
- **Observation:** a source-backed assertion about an entity.
- **Representation:** a versioned geometry or attribute depiction.
- **Source record:** what an upstream source supplied.
- **Artifact:** an immutable payload or file.
- **Relationship:** a typed connection between entities or records.
- **Capability:** a versioned contract for a computation.
- **Geo-Cell:** a declarative instance of a computation.
- **Recipe:** a versioned composition of computations.
- **Run:** an immutable execution attempt and its lineage.
- **Validation evidence:** a record of what was assessed and what remains unknown.

These concepts have different identities and lifecycles. They must not be collapsed into one universal record type.

## Architectural layers

1. **Spatial information core:** identity, versions, observations, representations, relationships, temporal state, and provenance.
2. **Ingestion and reconciliation:** source registration, import, normalization, entity matching, conflict handling, and controlled acceptance of information.
3. **Spatial query and services:** entity retrieval, spatial search, history, relationship traversal, and exports.
4. **Computation and transformation:** Capabilities, Geo-Cells, Recipes, Runs, workers, Artifacts, and independent validation.
5. **Application and agent interfaces:** products, APIs, SDKs, analytical tools, and optional AI-assisted workflows.

The current repository's contracts-first computation system is a substantial foundation for layer four. It remains valuable, but it is no longer the entire definition of Foundry.

## First bounded proof: road-network information

Foundry should prove its persistent information model in one bounded domain before attempting universal coverage.

The initial domain is road networks, with a small entity vocabulary such as RoadSegment, Junction, and RoadNetwork. The first study area and source set will be chosen after inspecting available data and the methods already documented in Spatial Methods.

The first end-to-end system should preserve an imported source snapshot, assign durable Foundry identities, maintain source crosswalks, store versioned geometries and attributes, represent network relationships, retain conflicting observations, expose query/history/provenance APIs, and export reproducible snapshots.

A computation using the existing Recipe and Run machinery should then demonstrate lineage from source records through entity versions to derived outputs.

## Relationship to Spatial Methods and products

**Spatial Methods** is the knowledge and methods foundation: mathematical and theoretical foundations, data acquisition, algorithms, implementations, and recipes.

**Foundry** is the operational infrastructure that persists and connects spatial information and executes governed computations.

**Tessellatum products** solve specific customer problems using these capabilities. They should consume Foundry services where doing so creates real value; they should not be forced to adopt the entire platform.

## Principles

1. Preserve original source material and human-authored inputs.
2. Separate identity from geometry, observations, and files.
3. Never silently overwrite information or erase provenance.
4. Distinguish valid time from recorded time where the domain requires it.
5. Make uncertainty, missing evidence, and source limitations visible.
6. Separate data validity, computational correctness, methodological suitability, positional accuracy, and legal permission.
7. Keep computation explicit, versioned, and reproducible.
8. Keep AI outside the trusted core; AI may propose, explain, and assist, but cannot silently rewrite source information or bypass validation.
9. Prefer one well-bounded vertical slice over a universal platform design.
10. Scale infrastructure only when workload, reliability, or customer demand requires it.

## What this vision does not claim

Foundry does not yet provide a universal global spatial database, complete digital twin, fully federated execution fabric, autonomous spatial agent, production marketplace, or production-grade multi-tenant hosted service. These are not prerequisites for the first useful system.

## Source of truth

- [Foundry reorientation](FOUNDRY_REORIENTATION.md) defines the proposed architecture and first milestone.
- [Project status](PROJECT_STATUS.md) records implemented behavior and verification evidence.
- [Architecture](../ARCHITECTURE.md) and [decision records](decisions/README.md) describe current technical constraints and why they exist.
- Capability contracts, tests, pull requests, and release evidence establish what actually works.

The vision describes direction; it does not override implementation evidence.
