# Tessellatum Foundry

Tessellatum Foundry is being developed as infrastructure for describing, composing, executing, validating, and reproducing spatial computations across compatible engines and execution environments.

The repository follows a contracts-first implementation sequence. The first milestone is a dependable, auditable spatial computation system—not a general-purpose GIS application and not an AI demo.

## Current status

- [x] Repository established.
- [x] Initial architectural decisions documented.
- [x] Core domain contracts drafted as JSON Schema.
- [x] v0.1 acceptance criteria documented.
- [x] Initial JSON Schema validator and Recipe graph semantic validator implemented with CI tests.
- [x] Initial spatial metadata and pre-execution CRS/unit validator implemented with tests.
- [x] Engine-independent vector.buffer contract implemented.
- [x] Independent Shapely and PostGIS vector.buffer adapters implemented on engine-neutral request validation, with native geometry checks in each engine.
- [x] Versioned implementation manifests registered and schema-validated.
- [x] Shared geometry conformance suite added, including topological comparison of both engine results.
- [x] GitHub Actions configured with a real PostGIS service for conformance testing.
- [x] PostGIS-backed CI conformance run verified green (91 tests passed).
- [~] Initial execution/output validator implemented for vector.buffer; methodological and rights/security policy validators remain outstanding.
- [~] First local single-cell execution path implemented for vector.buffer; Recipe orchestration and general execution remain outstanding.
- [ ] Remote worker path implemented and conformance-tested.
- [ ] Initial raster capabilities implemented.
- [ ] Read-only recipe graph viewer implemented.

Items are marked complete when implementation and corresponding tests are present. Runtime and CI verification are reported separately.

## Start here

1. [Architecture](ARCHITECTURE.md)
2. [Decision register](docs/decisions/README.md)
3. [Schemas](schema/)
4. [v0.1 acceptance criteria](tests/acceptance/README.md)

## Foundational model

1. **Artifact** — a versioned data object.
2. **Capability** — a versioned contract describing an operation.
3. **Geo-Cell** — a declarative, versioned instance of a computation.
4. **Run** — one attempt to execute a Geo-Cell.
5. **Recipe** — a versioned graph composing Geo-Cells.

The Validation Report is a separate evidence object. Implementations are registered separately from capability contracts.

## Development principles

- Contracts precede implementations.
- A schema-valid object is not necessarily semantically valid.
- Execution is deterministic where the capability permits it and always auditable.
- Every run records the exact versions and inputs it used.
- Workers are replaceable, but must conform to a shared execution contract.
- Capability implementations must pass conformance tests before being treated as interchangeable.
- The planner is optional and never required by the execution core.
- Security, provenance, licensing, and cost visibility are architectural concerns.

## First capability: vector.buffer

`vector.buffer@1.0.0` supports Point, MultiPoint, LineString, MultiLineString, Polygon and MultiPolygon inputs. It requires an explicit projected measurement CRS equal to the input CRS, rejects invalid input geometries rather than repairing them, and returns valid Polygon/MultiPolygon outputs while preserving feature IDs and properties. Its first two independent realizations are Shapely and PostGIS; both use the same semantic request validator. The PostGIS adapter requires an unambiguous EPSG CRS and checks the output SRID. Both implementations passed the shared geometry conformance suite in [CI run 173](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/42486888151): Ruff passed, 8 schemas, 7 fixtures, 1 capability contract and 2 implementation manifests validated, and 91 tests passed. The conformance manifests record suite version 0.1.0 as passed. The claim is limited to the declared contract and tested conformance cases/tolerances; it does not imply byte-identical geometry encodings.

Implementation manifests are stored separately under `implementations/`; their conformance status remains `not_run` until the PostGIS-backed CI suite passes. Install the Shapely backend with the `shapely` extra or the PostGIS backend with the `postgis` extra. The PostGIS adapter does not import or require Shapely. Development installs both extras through `requirements-dev.txt`.

## First local execution slice\n\nThe initial execution service accepts one exact vector.buffer Geo-Cell version with one immutable vector Artifact input. It snapshots the exact Capability and cell versions, Artifact checksum, normalized parameters, implementation, worker and runtime image ID. Shapely executes in a network-disabled, read-only-root, non-root Docker container with resource and file-size limits. The control plane resolves the worker against a schema-validated implementation manifest and requires passed conformance for the exact Capability version. It validates the input request and Artifact geometry metadata before dispatch; the worker repeats request validation, and the host independently validates the result before registering an immutable output Artifact. Failed or timed-out retryable attempts remain immutable and retries create new Run records. This is a local demonstrator, not yet a Recipe scheduler or production multi-tenant sandbox. See [ADR-018](docs/decisions/018-first-local-run-and-isolated-worker.md).\n\n## Scope boundary

This repository is Tessellatum Foundry. It is an independent project with its own architecture, implementation, and lifecycle.
