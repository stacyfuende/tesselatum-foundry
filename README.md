# Tessellatum Foundry

Tessellatum Foundry is the engineering foundation for **unified infrastructure for spatial data**.

Foundry's primary responsibility is to make spatial information persistently identifiable, structured, versioned, connected, traceable, queryable, and usable by software. It will manage the lifecycle of geographic entities, source records, observations, geometries, attributes, relationships, provenance, and temporal history—and provide governed computation and service interfaces over that information.

The repository already contains a substantial contracts-first spatial computation system. That work is retained as Foundry's computation and transformation layer; it is not the whole definition of Foundry.

**Strategic direction:** [Foundry reorientation](docs/FOUNDRY_REORIENTATION.md)  
**Project vision:** [Unified spatial information infrastructure](docs/PROJECT_VISION.md)  
**Initial spatial information model:** [Entity, source, observation, representation, and relationship model](docs/SPATIAL_INFORMATION_MODEL.md)  
**Initial database migrations:** [PostgreSQL/PostGIS migrations](db/README.md)  
**Large-data architecture:** [Storage and processing architecture](docs/STORAGE_AND_PROCESSING_ARCHITECTURE.md)  
**Python information adapter:** [PostGIS repository package](src/tessellatum_foundry/information/)

## Architectural layers

1. **Spatial information core** — entity identity, source records, observations, versioned representations, relationships, temporal state, and provenance.
2. **Ingestion and reconciliation** — source registration, imports, normalization, entity matching, conflict handling, and controlled acceptance of information.
3. **Spatial query and services** — entity lookup, spatial search, history, relationship traversal, and exports.
4. **Computation and transformation** — the existing Artifacts, Capabilities, Geo-Cells, Recipes, Runs, workers, and validation evidence.
5. **Application and agent interfaces** — APIs, SDKs, products, analytical tools, and optional AI-assisted workflows.

## First bounded proof

The first domain for the persistent information model is **road networks**. The initial study area and source set will be selected after inspecting candidate data and the existing Spatial Methods repository.

The first end-to-end milestone will preserve a source snapshot, assign durable Foundry entity IDs, maintain source crosswalks, store versioned road geometries and attributes, represent network relationships, retain conflicting observations, expose query/history/provenance APIs, and export reproducible snapshots. It will then demonstrate a computation whose outputs trace back to exact source and entity versions.

Foundry 0.1 is not a universal global database, a new desktop GIS, a general arbitrary-code execution service, or an autonomous AI system. It should begin as a small, testable system with one PostgreSQL/PostGIS database, one API, object storage when required, and background workers where needed.

## Initial information model status

The first PostGIS migrations, data-model specification, and large-data storage boundary are present on the reorientation branch. They are **proposed and not yet runtime-verified**. They do not alter the existing filesystem Artifact, definition, or Run stores. See [ADR-045](docs/decisions/045-spatial-information-core.md).

## Existing computation foundation

The current computation subsystem is implemented around these concepts:

1. **Artifact** — an immutable, versioned data payload.
2. **Capability** — a versioned contract describing an operation.
3. **Geo-Cell** — a declarative, versioned instance of a computation.
4. **Run** — one execution attempt with recorded inputs, outputs, and lineage.
5. **Recipe** — a versioned graph composing Geo-Cells.
6. **Validation Report** — evidence describing checks and findings.
7. **Implementation** — a replaceable realization of a Capability, admitted through conformance.

The current repository includes JSON Schema and semantic validation, vector.buffer and vector.reproject implementations, Shapely/PostGIS conformance, immutable Cell and Recipe definition storage, isolated Docker execution, sequential mixed-capability Recipe execution, a local Python SDK, a read-only Recipe viewer, deterministic caching, and authenticated remote worker transport.

This is valuable infrastructure, but it is not yet the persistent geographic entity platform described by the new direction. The first optional PostgreSQL information repository adapter now exists on the reorientation branch. The authenticated multi-tenant network API, generated client SDK, ingestion pipeline, and production service boundary remain to be built.

## Current computation status

- [x] Repository and architectural decision register established.
- [x] Core computation contracts drafted as JSON Schema.
- [x] JSON Schema and Recipe graph semantic validators implemented with CI tests.
- [x] Spatial metadata, CRS and measurement-unit validation implemented.
- [x] Engine-independent vector.buffer contract and shared request validator implemented.
- [x] Independent Shapely and PostGIS vector.buffer implementations pass shared geometry conformance.
- [x] Canonical Capability registry and conformance-gated implementation registry implemented.
- [x] Immutable versioned Cell and Recipe definition storage implemented.
- [x] Local Docker execution path for vector.buffer implemented and integration-tested.
- [x] Sequential Recipe runner resolves upstream Runs to immutable Artifacts and preserves node lineage.
- [x] Installed distribution packages schemas, Capability contracts, and implementation manifests.
- [x] Minimal local Python SDK composes canonical registries, immutable stores, and sequential Recipe execution.
- [~] Execution/output validation and methodological evidence exist for vector.buffer and vector.reproject; analytical suitability, area-of-use/accuracy review, and authoritative rights/security policy evaluation remain outstanding.
- [~] Recipe orchestration dispatches through exact capability-version runner registrations. Parallel scheduling remains outstanding.
- [~] Authenticated HTTPS remote worker adapter and HTTP execution service exist; deployment hardening and end-to-end remote conformance remain outstanding.
- [~] Initial raster capability is under review; Run/Artifact/Recipe integration and CI verification remain outstanding.
- [x] Dependency-free read-only Recipe DAG viewer implemented.
- [x] Deterministic execution cache with immutable output reuse and validation-gated cache reuse implemented.
- [~] Local Python SDK is available; authenticated network API and generated client SDK remain outstanding.

Implementation and verification are reported separately. A checked implementation item does not imply production readiness.

## Python SDK

The local SDK is the first convenience interface over the canonical computation contracts:

```bash
pip install 'tessellatum-foundry[shapely]'
```

```python
from pathlib import Path
from tessellatum_foundry import LocalFoundry

foundry = LocalFoundry(Path("./foundry-data"))
foundry.register_cell(cell_definition, created_by="local-operator")
foundry.register_recipe(recipe_definition, created_by="local-operator")

result = foundry.execute_recipe(
    recipe_id="site-selection",
    version="1.0.0",
    actor_id="local-operator",
)
print(result.status, result.execution_id)
```

This is a local SDK, not an authenticated network API or multi-tenant service. See [ADR-025](docs/decisions/025-local-python-sdk.md).

## Read-only Recipe viewer

Open [viewer/index.html](viewer/index.html) in a browser, then paste a canonical Recipe JSON document or select it from disk. The viewer renders exact Geo-Cell references, directed port dependencies, topological depth, and declared outputs. It does not edit or execute a Recipe. See [viewer documentation](viewer/README.md) and [ADR-028](docs/decisions/028-read-only-recipe-viewer.md).

## Start here

1. [Foundry reorientation](docs/FOUNDRY_REORIENTATION.md) — the new architectural direction and first end-to-end milestone.
2. [Project vision](docs/PROJECT_VISION.md) — the role of Foundry in Tessellatum's unified spatial information infrastructure.
3. [Spatial information model](docs/SPATIAL_INFORMATION_MODEL.md) — initial persistent entity and provenance model.
4. [Project status](docs/PROJECT_STATUS.md) — current implementation, open work, verification gates, and hand-off notes.
5. [Architecture](ARCHITECTURE.md) — current computation architecture; subject to alignment with the reorientation.
6. [Decision register](docs/decisions/README.md) — accepted technical decisions and their rationale.
7. [Schemas](schema/) — current computation contracts.
8. [v0.1 acceptance criteria](tests/acceptance/README.md).

## Development principles

- Preserve original source data and human-authored information.
- Separate geographic identity from files, observations, geometries, and computation outputs.
- Contracts precede implementations.
- Schema validity is not semantic validity or methodological suitability.
- Every computation records exact versions, inputs, implementations, and provenance.
- Outputs are independently inspected before immutable registration or cache reuse.
- Workers are replaceable but must conform to shared execution contracts.
- AI is optional and must not be required in the trusted execution core.
- Security, provenance, licensing, uncertainty, and cost visibility are architectural concerns.
- Build one useful vertical slice before generalizing.
- Scale infrastructure only when workload and customer demand justify it.

## Repository boundary

This repository is Tessellatum Foundry. It is an independent project with its own architecture, implementation, and lifecycle. Spatial Methods remains the companion knowledge and methods repository; customer-facing products consume Foundry capabilities where they provide real value.
