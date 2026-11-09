# Project vision

**Status:** Foundational product vision; intentionally broader than the current implementation.  
**Role of this document:** Preserve the original ambition and explain how the Foundry repository is intended to contribute to it. This is a living product-level document, not an implementation checklist or an architecture specification.

## The ambition

Tessellatum is conceived as an AI-native environment for creating, composing, executing, understanding, and sharing geospatial work.

The long-term idea is larger than a collection of GIS algorithms or a wrapper around existing spatial engines. It is a platform in which spatial data, computational capabilities, dependencies, context, and results can be expressed in a common model. People should be able to describe a spatial goal, have the system help turn that intent into an explicit workflow, inspect and refine the workflow, execute it using appropriate tools, and understand why its outputs should be trusted.

The platform should make geospatial computation more composable and accessible without hiding the semantics, provenance, limitations, or methodological choices that make spatial results meaningful.

## Founding ideas

The original concept notes describe several connected ideas. They are aspirations and design directions, not claims that all of these capabilities exist today.

### 1. A common spatial abstraction

The early Geo-Cell idea aimed to provide a common way to describe spatial data and computation: what goes in, what operation is performed, what comes out, and what dependencies and context matter.

The purpose is to let different engines and services participate in a larger computation without requiring every user to understand each engine's internal API.

### 2. A universal capability interface

Spatial operations may be implemented by different technologies, services, and execution environments. A common capability description should make those implementations discoverable and comparable against shared semantics.

The contract is the stable interface; an implementation is a replaceable realization of that contract. Compatibility must be demonstrated through conformance, not assumed because two tools have similar names.

### 3. Intent-driven orchestration

A user should ultimately be able to express a spatial objective in natural language or through a visual workflow. The system can help translate that intent into an explicit, inspectable sequence of spatial operations, data dependencies, and outputs.

The orchestration layer should not make the computation opaque. Plans should be reviewable, editable, reproducible, and executable independently of any particular conversational interface.

### 4. Independent spatial critique

The original Spatial Critic idea is to assess whether a computation and its outputs satisfy declared requirements and to surface limitations that matter to interpretation.

This is more than checking whether code ran or whether an output matches a schema. Validation should be explicit about what was checked, what evidence supports a finding, what remains unknown, and which questions require domain context or external authority.

### 5. Reusable spatial recipes

Spatial workflows should be expressible as reusable, versioned compositions. A recipe should make its operations, dependencies, inputs, outputs, and provenance understandable so that work can be repeated, reviewed, shared, and evolved.

### 6. A visual and conversational creation experience

The intended product experience includes both conversation and visual interaction. Users should be able to create and refine maps, analyses, dashboards, and applications while retaining visibility into the underlying workflow.

The interface is a way into the platform, not a substitute for explicit computational definitions and evidence.

### 7. An extensible ecosystem

The longer-term direction includes contributions from developers, data providers, specialized engines, and domain-specific services. A shared capability model and reliable execution boundaries can provide the basis for such an ecosystem.

A marketplace, broad federation, and open ecosystem are future possibilities—not current repository features.

### 8. Applied spatial products

The original notes also considered concrete applications, including SiteSelector, spatial audits, and synthetic-data services. These are examples of how platform capabilities might be assembled into useful products.

SiteSelector is an application direction, not the definition or limit of Tessellatum itself.

## What Tessellatum Foundry is building now

Tessellatum Foundry is the foundational engineering layer of this broader direction. Its immediate job is to make spatial computation explicit, composable, independently validated, and reproducible.

The current model is built around:

- **Artifact:** a versioned data object.
- **Capability:** a versioned, engine-independent description of an operation.
- **Geo-Cell:** a declarative, versioned instance of a computation.
- **Run:** an execution attempt with an immutable record of what was used and what happened.
- **Recipe:** a versioned graph composing Geo-Cells.
- **Validation Report:** a separate evidence object describing checks and findings.
- **Implementation:** a replaceable realization of a Capability, registered separately and admitted through conformance.

This model is the practical foundation for the common abstraction, capability interface, recipe composition, and independent critique described above.

## How the vision maps to the work

| Founding idea | Foundry foundation | Current position |
|---|---|---|
| Common spatial abstraction | Artifacts, Geo-Cells, versioned contracts, spatial metadata | Core foundations implemented; abstraction continues to evolve |
| Universal capability interface | Canonical Capability contracts, implementation registry, conformance suites | Implemented for initial vector capabilities; more capability families remain |
| Intent-driven orchestration | Recipe graph validation and deterministic execution | Explicit Recipe execution exists; natural-language planning is future work |
| Independent Spatial Critic | Separate Validation Reports and operation-specific output critics | Initial vector validation and methodological evidence exist; broader domain critique remains |
| Reusable spatial recipes | Immutable Recipe definitions, dependency graphs, Run and Artifact lineage | Sequential execution and mixed vector recipes exist; parallel scheduling and broader composition remain |
| Visual/conversational creation | Read-only Recipe DAG viewer and inspectable definitions | A read-only viewer exists; full interactive authoring and conversational creation remain future work |
| Extensible ecosystem | Replaceable workers, remote worker transport, conformance-gated implementations | Initial local and remote boundaries exist; production federation and ecosystem tooling remain future work |
| Applied products | Reusable platform capabilities and SDK | SiteSelector and other application layers are not the current Foundry implementation scope |

For the authoritative implementation inventory, open [Project status and collaboration guide](PROJECT_STATUS.md). For technical decisions and rationale, consult the [decision register](decisions/README.md) and [architecture](../ARCHITECTURE.md).

## Product boundaries and principles

The ambition is broad, but the platform should grow through verifiable foundations rather than claims.

1. **Keep computation explicit.** A user-friendly interface must not conceal the actual operations, parameters, dependencies, or data assumptions.
2. **Separate contracts from implementations.** Implementations can change; declared semantics and conformance expectations must remain reviewable.
3. **Treat evidence as a first-class output.** A successful process exit is not proof that a spatial result is correct or suitable.
4. **Preserve provenance.** Inputs, versions, implementation identity, execution context, and output lineage should be traceable.
5. **Distinguish validity from suitability.** Schema validity, technical correctness, methodological appropriateness, positional accuracy, and legal permission are different questions.
6. **Make uncertainty visible.** Missing evidence must remain unknown or unassessed rather than being silently treated as success.
7. **Keep orchestration separable.** Conversational planning may assist users, but the execution core should accept explicit, validated definitions.
8. **Grow through conformance.** New engines and capabilities should join through shared contracts and tests, not one-off special cases.
9. **Build the platform before overfitting to one application.** Specific applications should demonstrate and use reusable platform capabilities without narrowing the platform's purpose.

## What this vision does not claim

The following remain future directions unless the status tracker and implementation evidence say otherwise:

- autonomous agents that reliably plan and execute arbitrary spatial projects;
- a planetary or universal spatial index;
- a complete universal spatial data model covering every geometry, raster, temporal, network, and 3D use case;
- automatic discovery and orchestration of every GIS engine or external data service;
- federated, globally distributed execution and a production marketplace;
- a full visual map, dashboard, and application builder;
- production-grade multi-tenant hosted services;
- finished SiteSelector, spatial-audit, or synthetic-data products.

These ideas may inform design, but they must not be represented as delivered functionality.

## How this document evolves

This document records the product direction and the relationship between that direction and the engineering foundation. Update it when the ambition, target users, product boundaries, or strategic sequencing materially change.

Use the companion documents for different kinds of truth:

- **This document — Project vision:** what the larger platform is for and the principles guiding it.
- **[Project status](PROJECT_STATUS.md):** what exists, what is in progress, what is blocked, and what remains.
- **[Architecture](../ARCHITECTURE.md) and ADRs:** how the system is designed and why specific decisions were made.
- **Capability contracts, tests, PRs, and release evidence:** the precise behavior that has actually been implemented and verified.

When these documents differ, implementation claims must be grounded in code, tests, and verification evidence. The vision describes direction; it does not override the evidence.
