# Tessellatum Foundry — Architecture

**Status:** Foundational architecture baseline  
**Version:** 0.1-draft  
**Normative language:** MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY express requirements and recommendations.

## 1. Purpose

Foundry provides infrastructure through which spatial computations can be declared, composed, executed, validated, inspected, and reproduced across compatible engines and execution environments.

A GIS application helps a person perform spatial work. Foundry aims to make spatial work composable and reusable across applications, teams, and systems.

The v0.1 objective is narrower: establish a dependable spatial computation engine with explicit contracts, isolated execution, immutable run history, and independently evaluated outputs.

## 2. Architectural invariants

1. Artifacts, capabilities, Geo-Cells, runs, and recipes are distinct entities with distinct identities and lifecycles.
2. A Geo-Cell is a declaration. It MUST NOT contain execution state, runtime implementation code, mutable output data, or machine-local file paths.
3. A Run is an execution attempt. Retrying creates a new attempt/run record; it MUST NOT rewrite an earlier outcome.
4. Artifact versions and capability versions referenced by a run MUST be immutable.
5. A Recipe is a graph of versioned Geo-Cells. It is not itself an execution.
6. The API and serialized contracts are canonical. User interfaces are clients or projections of those contracts.
7. Schema validation and semantic validation are separate stages.
8. The execution core accepts fully resolved, validated computation declarations. A language model is never required to execute them.
9. Workers implement a shared execution protocol while advertising their actual capabilities and constraints.
10. A successful process exit or a created output file is not sufficient evidence of spatial correctness.
11. Provenance, licensing, security, and resource accounting MUST be represented rather than assumed.

## 3. Domain model

### 3.1 Artifact

An Artifact is a logical data object with one or more immutable versions. A version identifies a specific content snapshot and carries its checksum, media type, storage reference, metadata, spatial characteristics where applicable, and rights information.

The same artifact version can be consumed by many cells and recipes. A computation does not own or mutate its input artifact. An artifact reference MUST identify both artifact ID and version. A moving alias such as latest is not a resolved run input.

### 3.2 Capability

A Capability is a versioned promise describing an operation, its input ports, parameters, output ports, preconditions, and validation expectations. For example, vector.buffer describes buffering semantics; it does not mean Shapely, PostGIS, or QGIS.

A capability contract is separate from its implementations. Each implementation declares the engine/runtime that realizes the contract and must pass the capability's conformance suite before being considered compatible.

Capability semantics MUST specify relevant details such as units, CRS handling, geometry dimensionality, precision expectations, invalid-geometry behaviour, and output guarantees. A shared name alone does not establish equivalence.

### 3.3 Geo-Cell

A Geo-Cell is a declarative, versioned instance of a computation. It binds:
- one exact capability version;
- named input ports to exact artifact versions;
- normalized parameters;
- declared output contracts; and
- applicable preconditions and validation requirements.

A Geo-Cell contains no implementation selection, execution state, logs, output bytes, or local filesystem paths. Those belong to the registry, Run, or Artifact domains.

A cell can be inspected and validated without being executed. Its version changes when its declarative meaning changes.

### Input bindings and graph edges

A Geo-Cell input port may bind either to an immutable Artifact version or to a named output port of another exact Geo-Cell version. The Recipe stores an explicit edge for each cell-to-cell dependency so that graph topology is directly inspectable and renderable. These are two representations of the same dependency: semantic graph validation MUST verify that every cell-output binding has exactly one matching Recipe edge and every Recipe edge matches the target cell's declared input binding. A mismatch invalidates the Recipe.

At execution time, each upstream cell output is resolved to the immutable Artifact version produced by that upstream Run. The downstream Run records the resolved artifact ID, version, and checksum in its input snapshots. This preserves reproducibility across the graph without requiring a not-yet-executed cell to invent an output artifact version.


### 3.4 Run

A Run is one attempt to execute one exact Geo-Cell version, optionally as part of a Recipe execution. It records resolved inputs, normalized parameters, selected implementation, worker, runtime image digest, resource use, timestamps, events, validation results, and produced artifact versions.

Runs are append-only historical records. State transitions are controlled and observable. A retry creates a new run linked to the prior attempt; it does not erase or mutate the prior run's terminal result.

### 3.5 Recipe

A Recipe is a versioned directed graph of Geo-Cell versions. Nodes are cells; edges connect named output ports to named input ports. Recipes may also expose external inputs and selected outputs.

The initial graph model is a directed acyclic graph (DAG). Cycles are rejected in v0.1. Iterative algorithms may be implemented internally by a capability, but the outer Recipe graph remains acyclic.

A Recipe version is immutable once used for execution. Editing a recipe creates a new version.

### 3.6 Validation Report

A Validation Report is an evidence object produced by a validator. It identifies the subject and validation stage, records an overall outcome, and contains findings with severity, status, evidence, and machine-readable codes.

Finding statuses distinguish passed, failed, warning, not_assessed, and requires_review. An overall report MUST NOT imply that an unassessed dimension passed.

### 3.7 Capability implementation

A capability implementation is a separately versioned realization of a capability contract. It records engine, runtime, implementation version, supported platforms, resource requirements, and conformance status. It is not the capability itself and is not embedded in a Geo-Cell.

## 4. Relationships

- One Artifact has many immutable versions.
- One Capability has many immutable contract versions.
- One Capability version may have multiple registered implementations.
- One Geo-Cell version references exactly one Capability version and zero or more exact Artifact versions.
- One Geo-Cell version may have many Runs.
- One Recipe version references one or more Geo-Cell versions and typed port edges.
- One Run produces zero or more Artifact versions and zero or more Validation Reports.
- A Validation Report refers to the exact subject/version and validation stage it assessed.

## 5. Contracts and validation

JSON Schema Draft 2020-12 defines the language-neutral structural contracts in schema/. YAML MAY be used as a human-friendly serialization format, but YAML documents MUST validate against the same JSON Schema contracts. The canonical schema files are JSON.

Validation is layered:

1. **Schema:** object shape, required fields, primitive types, enumerations, and local conditional structure.
2. **Reference:** existence and immutability of referenced IDs and versions.
3. **Graph:** port existence, port compatibility, edge integrity, acyclicity, and recipe input/output consistency.
4. **Spatial:** CRS, units, geometry types, extents, raster grids, dimensions, and other spatial metadata.
5. **Methodological:** suitability of the declared method for the stated analytical purpose. This may require domain-specific rules or human review.
6. **Execution/output:** actual outputs conform to declared contracts and satisfy configured checks.
7. **Rights/security policy:** the requested use is permitted and execution is authorized.

JSON Schema cannot establish cross-object or data-dependent truths. Those rules belong in semantic validators and runtime checks. Python is the initial implementation language for those validators; client types may be generated from the canonical schemas.

### Spatial metadata and pre-execution validation

Spatial Artifact metadata for vector, raster, point-cloud, and mesh data MUST declare a resolvable CRS. Raster artifacts MUST also declare grid dimensions. Capability input and output ports MAY declare machine-readable spatial constraints: required CRS, CRS kind, accepted geometry types, and equality with another named input port's CRS.

Foundry interprets extents in GIS x/y order, independent of the authority axis order recorded by a CRS: a 2D extent is [min_x, min_y, max_x, max_y]; a 3D extent is [min_x, min_y, min_z, max_x, max_y, max_z]. Extents MUST be finite and ordered. For geographic CRSs, x/y bounds are checked against the longitude/latitude domain after accounting for the CRS angular units. Antimeridian-crossing extents must be split or represented by a future explicit wrap-aware extent type; a reversed min/max extent is not a wrap encoding.

The initial spatial validator uses PROJ through pyproj to resolve CRS definitions and inspect CRS kinds and axis units. If a Geo-Cell declares a linear measurement unit, it MUST also declare a measurement CRS; that CRS MUST be projected and its horizontal axis units MUST match the declared unit. A Capability MAY bind a normalized measurement parameter to a linear or area unit kind; the Geo-Cell parameter and its corresponding unit constraint MUST be equivalent. Supported area units are validated against Foundry's explicit unit vocabulary. This check does not imply or authorize implicit reprojection of input data. Any transformation required by a workflow must be represented explicitly by a computation or by a separately specified capability contract.

Validation is evidence-producing. Validators MUST report what they assessed, what they did not assess, and the evidence supporting each finding. The Spatial Critic is logically independent from the planner and must not silently repair a graph or rewrite a result.


### First executable capability: vector.buffer

The first executable operation is `vector.buffer@1.0.0`, with its engine-independent contract registered under `capabilities/` and an initial Shapely realization in `src/tessellatum_foundry/capabilities/vector_buffer.py`. The operation is planar and requires the input CRS to equal an explicitly declared projected measurement CRS. Distance is expressed in the CRS's native horizontal unit; no implicit reprojection, unit conversion, or geometry repair occurs. Input geometries must be non-empty and valid. Output geometries must be valid Polygon or MultiPolygon values, and feature IDs and properties are preserved. These guarantees are tested at the geometry-operation boundary, but the implementation is not yet connected to the Run lifecycle or artifact persistence.

## 6. Control plane and compute plane

### Control plane

The control plane owns schema and semantic validation, artifact and capability references, Geo-Cell and Recipe versions, dependency resolution, worker selection and scheduling, run lifecycle and event records, cache decisions, and policy enforcement.

### Compute plane

The compute plane owns isolated workers, runtime adapters and engine environments, execution of a resolved Run specification, resource enforcement, output staging, and structured execution results.

The control plane submits the same logical Run specification regardless of worker location. Workers advertise supported capability implementations, runtime constraints, and resource limits. The scheduler MUST NOT assume all workers can execute all capabilities.

v0.1 includes a local Docker worker and a simple remote worker protocol. The remote worker is not a Kubernetes commitment. Both paths must satisfy the same protocol and conformance tests.

## 7. Execution lifecycle

### Cell lifecycle

A cell definition may move through draft, validated, and ready. These describe declaration readiness, not execution outcome.

### Run lifecycle

A run may move through queued, waiting_for_resources, and running, then reach a terminal state: succeeded, failed, cancelled, or timed_out. A retry creates a new Run with a new run ID, an incremented attempt number, and retry_of_run_id pointing to the previous attempt; retrying is not a status of the previous Run.

Terminal runs are immutable. Retry policy creates a new attempt with an explicit relationship to the previous attempt. Run events provide an auditable transition history.

### Execution record

At minimum, a completed run records:
- exact cell ID and version;
- exact capability ID and version;
- exact artifact IDs and versions for all inputs;
- canonical normalized parameters;
- implementation ID and version;
- worker identity and worker type;
- runtime/container image digest;
- start/end timestamps and resource use;
- output artifact IDs and versions;
- validation report references; and
- structured failure information when unsuccessful.

## 8. Determinism, caching, and reproducibility

A capability declares whether it is deterministic, conditionally deterministic, or nondeterministic. Random seeds, model versions, external data snapshots, and relevant runtime settings are explicit inputs to reproducibility.

A cache key SHOULD include capability and contract version, implementation version, immutable input artifact checksums, canonical normalized parameters, runtime image digest, relevant configuration, external source snapshot identifiers, and random seed/model version where applicable.

A cache hit is valid only when all declared cache-relevant inputs match and the previous result passed the required validation policy. Nondeterministic capabilities require explicit cache policy and MUST NOT be treated as deterministic by default.

## 9. Capability portability and conformance

A capability contract describes semantics, not an engine. Multiple implementations may satisfy the same contract, but they are interchangeable only to the extent established by a conformance suite.

Conformance tests must cover relevant edge cases, units, CRS behaviour, geometry validity, precision tolerances, null handling, output structure, and failure semantics. Floating-point and geometry outputs may require declared tolerances rather than byte equality.

Foundry records the implementation actually used by every Run. Automatic engine optimization is out of scope until multiple implementations have demonstrated conformance and operational reliability.

## 10. Initial capability scope

The initial library is intentionally small:
- file ingestion;
- vector buffer;
- vector clip;
- vector spatial join;
- vector CRS transformation; and
- raster zonal statistics.

Each capability must have a precise contract. At least one capability—initially vector.buffer—must have two independent implementations that pass the same conformance suite before v0.1 is considered complete.

## 11. Security, rights, and isolation

Capabilities execute code and must be treated as a security boundary. The execution design MUST account for non-root execution, isolated worker filesystem/process boundaries, CPU/memory/disk/wall-clock limits, scoped credentials and secret handling, controlled network egress, tenant and artifact access controls, audit events, and licence/attribution/redistribution/permitted-use metadata.

Arbitrary user-supplied code is out of scope for v0.1. Security is not postponed until a public marketplace exists.

## 12. Interfaces and agent boundary

The API and SDK are canonical interfaces to the domain model. A minimal read-only Recipe viewer is a projection of the same serialized Recipe and must not become a second source of truth.

A planner may translate natural language or templates into a proposed Recipe. It is optional, replaceable, and outside the deterministic execution core. Every proposed Recipe must pass the same validation and authorization gates as one created through the API or viewer. A planner cannot bypass validation or directly execute arbitrary tools.

## 13. v0.1 demonstrator

The first end-to-end demonstrator will:
1. ingest a real vector dataset;
2. create immutable artifact metadata and checksum;
3. declare a Geo-Cell using vector.buffer;
4. compose a valid Recipe;
5. validate schema, references, graph, and spatial constraints;
6. execute through a local worker;
7. validate and register the output artifact;
8. record complete run provenance;
9. rerun unchanged inputs and demonstrate a valid cache hit; and
10. change a parameter and demonstrate selective recomputation.

A raster workflow follows once the vector path is reliable. The second implementation of vector.buffer is required to validate the capability abstraction.

## 14. Explicit non-goals for v0.1

- A large general-purpose GIS algorithm catalogue.
- Automatic engine optimization.
- Kubernetes or globally distributed compute.
- Federated execution across arbitrary organizations.
- Agent-to-agent execution.
- A universal spatial index or forced universal data format.
- A public capability marketplace.
- Arbitrary user scripts.
- A full visual workflow editor.
- A natural-language agent as the primary interface.

## 15. Definition of architectural success

Foundry succeeds at this stage when a computation can be declared without running it, validated before execution, run on a compatible worker, independently checked, traced to exact immutable inputs and implementation versions, and reproduced or safely cache-reused with explicit evidence.

The implementation is not complete merely because the API responds or a container exits successfully. It is complete when acceptance tests demonstrate the contracts and failure behaviours described here.
