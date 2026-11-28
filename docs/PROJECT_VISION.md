# Project vision

**Status:** Current strategic direction  
**Date:** 2026-11-22

## The ambition

Tessellatum's north star is **unified infrastructure for spatial data**.

Tessellatum Foundry is the computational foundation for that ambition. It makes spatial data usable across providers, formats, engines, workflows, applications and teams. It supplies the contracts and runtime through which spatial operations can be declared, composed, executed, validated and reproduced.

The ambition is not to centralize every spatial dataset. The world's spatial data is too large, distributed, dynamic, licensed and operationally diverse for a single platform to own sensibly. Foundry should connect to data where it already lives and make it computable.

## What Foundry owns

- Versioned, engine-independent spatial Capability contracts.
- Conformant implementations across suitable computational engines.
- Declarative Geo-Cells and composable Recipe graphs.
- Execution planning, worker dispatch and resource controls.
- Run lifecycle, immutable provenance and retry history.
- Independent validation and methodological evidence.
- Definitions, execution records, cache metadata and derived Artifacts.
- Stable APIs and SDKs for products, analysts and other software.

Foundry does not own source datasets by default. Source providers, customers or their chosen storage systems retain custody, access control and retention responsibility.

## What Foundry does with external data

Foundry connects to local, customer-controlled or provider-hosted sources. It resolves the requested data, checks access and metadata, reads bounded windows or streams into workers, and records source references and reproducibility evidence. It should use provider-side filtering and query pushdown where possible.

If a source cannot provide an immutable version or checksum, Foundry records that limitation rather than pretending that a URL is a reproducible snapshot. Customers may choose to retain snapshots under their own storage policy. Foundry does not silently mirror entire datasets.

## The computational model

- **Capability:** a versioned contract defining an operation's semantics and constraints.
- **Implementation:** a replaceable engine-specific realization that passes conformance.
- **Geo-Cell:** a declarative, versioned instance of a computation.
- **Recipe:** a directed graph composing Geo-Cells and their data dependencies.
- **Run:** an immutable execution attempt with resolved inputs, outputs and lineage.
- **Artifact:** an immutable computational input or output payload managed under an explicit policy.
- **Validation Report:** evidence about the exact subject assessed, including limitations and unknowns.
- **External Data Reference:** a locator and provenance description for source data that remains outside Foundry's custody.

These concepts have different identities and lifecycles. A source reference is not a source copy; an Artifact is not a geographic entity; and a successful Run is not proof of authoritative inputs or universal suitability.

## Architecture

1. **Control plane:** contracts, definitions, graph validation, source resolution, authorization, scheduling, Run lifecycle, provenance and cache decisions.
2. **Compute plane:** isolated workers, capability implementations, bounded data reads, temporary scratch, output staging and resource accounting.
3. **External data plane:** providers, customer databases, object stores, local files and query services that retain ownership of their data.
4. **Artifact plane:** optional storage for definitions, execution evidence, cache entries and derived outputs under explicit lifecycle policies.
5. **Application interfaces:** APIs, SDKs, products, analytical tools and optional agents.

The planes describe responsibilities; they do not require a distributed deployment.

## Relationship to Spatial Methods and products

**Spatial Methods** is the knowledge and methods repository: theory, algorithms, acquisition methods, implementations, experiments and tested recipes.

**Foundry** is the computational substrate that makes those methods executable, composable, testable and reusable against external spatial data.

**Tessellatum products** solve specific customer problems. They should consume Foundry capabilities when doing so creates real value, not be forced to adopt every platform feature.

## Principles

1. External data stays external by default.
2. Read only what a computation needs; prefer streaming, windows, pagination and pushdown.
3. Never silently copy, mutate or claim ownership of source data.
4. Record source identity, version evidence, query parameters and limitations.
5. Separate data validity, computational correctness, methodological suitability, accuracy, authority and legal permission.
6. Keep computation explicit, versioned and reproducible.
7. Validate outputs independently before artifact registration or cache reuse.
8. Keep AI optional and outside the trusted execution core.
9. Build one useful vertical workflow before generalizing.
10. Scale compute and artifact storage based on measured workloads and customer requirements.

## What this vision does not claim

Foundry is not yet a production-grade multi-tenant service, universal connector fabric, federated query engine, general-purpose GIS replacement, global data warehouse or autonomous spatial agent. These are not prerequisites for proving the computational foundation.
