# Tessellatum Foundry

Tessellatum Foundry is the engineering foundation for **unified infrastructure for spatial data**.

Foundry makes spatial data computable across formats, engines, workflows, and applications. It provides stable contracts for capabilities, declarative Geo-Cells, composable Recipes, controlled execution, independent validation, immutable computational artifacts, and traceable Runs.

**Foundry does not aim to own or permanently host the world's spatial datasets.** Data remains with its provider, customer, or chosen storage system wherever practical. Foundry connects to data through explicit adapters, reads only what a computation needs, and records references and provenance sufficient to explain what was used. It persists computation definitions, execution records, validation evidence, and derived outputs when those are part of the product contract—not wholesale copies of upstream datasets.

## Responsibility boundary

| Concern | Foundry's role |
|---|---|
| External spatial data | Connect, inspect, stream/read bounded inputs, and respect provider access rules |
| Data ownership and retention | Remain with the source owner or their storage platform |
| Computation | Define and execute versioned spatial capabilities |
| Composition | Connect Geo-Cells into validated Recipes |
| Execution | Dispatch to compatible, isolated workers |
| Validation | Independently inspect inputs, outputs, and methodological evidence |
| Provenance | Record exact source references, versions/checksums where available, parameters, implementation, runtime and lineage |
| Outputs | Register derived artifacts and execution evidence under explicit retention policy |
| Applications | Expose stable SDK/API contracts for products and tools |

## Core model

1. **Capability** — a versioned, engine-independent contract for an operation.
2. **Implementation** — a replaceable engine-specific realization admitted through conformance.
3. **Geo-Cell** — a declarative, versioned instance of a computation.
4. **Recipe** — a versioned directed graph composing Geo-Cells.
5. **Run** — an execution attempt with resolved inputs, outputs, events and lineage.
6. **Artifact** — an immutable computational input or output payload managed under an explicit storage policy.
7. **Validation Report** — evidence describing checks, findings, limitations and the exact subject assessed.
8. **External Data Reference** — a locator and provenance description for data that Foundry does not own.

An external reference is not a copy, a canonical geographic entity, or a guarantee that the remote resource will remain available. Reproducibility claims must state what was captured (for example provider/version/ETag/checksum/query/time) and what cannot be guaranteed.

## Current computation foundation

The repository includes JSON Schema and semantic validation, spatial metadata and CRS/unit checks, a canonical Capability registry, conformance-gated implementations, vector.buffer and vector.reproject, Shapely/PostGIS implementations, immutable Cell and Recipe definitions, isolated Docker execution, sequential mixed-capability Recipe execution, a local Python SDK, a read-only Recipe viewer, deterministic caching, authenticated remote worker transport, and independent output critics.

The current system is a useful local computation platform. It is not yet a production-grade multi-tenant hosted service, a general federated query fabric, or a universal connector catalogue.

## Engineering priorities

1. Complete and harden the execution lifecycle and worker resource controls.
2. Integrate raster computation into the same Run/Artifact/Recipe lifecycle.
3. Introduce a small external-data adapter contract that avoids mandatory bulk ingestion.
4. Record source references and their reproducibility limits in Run provenance.
5. Deliver an authenticated project/Cell/Recipe/Run/Artifact API and client SDK.
6. Build a usable workspace and Recipe Studio against the canonical contracts.
7. Expand capability coverage based on real workflows and customer demand.

## Spatial Methods and products

**Spatial Methods** remains the knowledge and methods repository: theory, algorithms, implementations, experiments and tested recipes.

**Foundry** is the reusable computational substrate that applies methods to spatial data and records the resulting work.

**Tessellatum products** solve specific customer problems. They should consume Foundry where it creates real value, not be forced to adopt every capability.

## Development principles

- External data stays external by default.
- Never silently copy, mutate, or claim ownership of source data.
- Prefer streaming, windowed reads, pushdown and bounded working sets over whole-dataset loading.
- Keep source access separate from computation contracts.
- Record exact inputs, versions, parameters, implementation and runtime.
- Validate outputs independently before registration or cache reuse.
- Distinguish computational correctness from methodological suitability, accuracy, authority and legal permission.
- AI remains optional and outside the trusted execution core.
- Build one useful end-to-end workflow before generalizing.
- Scale workers and storage according to measured workloads; do not impose free-tier limits or premature distributed infrastructure.

## Start here

1. [Foundry architecture](docs/FOUNDRY_REORIENTATION.md)
2. [Project vision](docs/PROJECT_VISION.md)
3. [External data source contract](docs/EXTERNAL_DATA_SOURCES.md)
4. [Current project status](docs/PROJECT_STATUS.md)
4. [Architecture](ARCHITECTURE.md)
5. [Decision register](docs/decisions/README.md)
6. [Schemas](schema/)
7. [v0.1 acceptance criteria](tests/acceptance/README.md)
