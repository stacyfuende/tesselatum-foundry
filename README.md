# Tessellatum Foundry

Tessellatum Foundry is being developed as infrastructure for describing, composing, executing, validating, and reproducing spatial computations across compatible engines and execution environments.

The repository follows a contracts-first implementation sequence. The first milestone is a dependable, auditable spatial computation system—not a general-purpose GIS application and not an AI demo.

## Current status

- [x] Repository and architectural decision register established.
- [x] Core domain contracts drafted as JSON Schema.
- [x] JSON Schema validator and Recipe graph semantic validator implemented with CI tests.
- [x] Spatial metadata, CRS and measurement-unit validation implemented.
- [x] Engine-independent vector.buffer contract and shared request validator implemented.
- [x] Independent Shapely and PostGIS vector.buffer implementations pass shared geometry conformance.
- [x] Canonical Capability registry and conformance-gated implementation registry implemented.
- [x] Immutable versioned Cell and Recipe definition storage implemented.
- [x] Local Docker execution path for one vector.buffer Geo-Cell implemented and integration-tested.
- [x] Sequential Recipe runner resolves upstream Runs to immutable Artifacts and preserves node lineage.
- [x] Installed distribution packages schemas, Capability contracts, and implementation manifests.
- [x] Minimal local Python SDK composes canonical registries, immutable stores, and sequential Recipe execution.
- [~] Execution/output validation is implemented for vector.buffer; methodological and rights/security policy validators remain outstanding.
- [~] Recipe orchestration dispatches through exact capability-version runner registrations; the only concrete Run service remains vector.buffer@1.0.0, and parallel scheduling remains outstanding.
- [ ] Remote worker path implemented and conformance-tested.
- [ ] Initial raster capabilities implemented.
- [x] Dependency-free read-only Recipe DAG viewer implemented.
- [x] Deterministic execution cache with immutable output reuse and parameter-based invalidation implemented; cache reuse requires current complete output-validation evidence.
- [~] Local Python SDK is available; authenticated network API and generated client SDK remain outstanding.

Items are marked complete when implementation and corresponding tests are present. Runtime and CI verification are reported separately.

## Python SDK

The local SDK is the first convenience interface over the canonical contracts. Install the Shapely extra for host-side output validation, then use an explicit persistent directory; execution defaults to the isolated Docker worker:

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

The facade also exposes `store_artifact`, `get_run`, `list_recipe_runs`, `get_artifact`, `get_validation_report`, and `read_artifact`. The latter verifies the Artifact checksum. This is a local SDK, not an authenticated network API or multi-tenant service. See [ADR-025](docs/decisions/025-local-python-sdk.md).

## Read-only Recipe viewer

Open [viewer/index.html](viewer/index.html) in a browser, then paste a canonical Recipe JSON document or select it from disk. The viewer renders exact Geo-Cell references, directed port dependencies, topological depth, and declared outputs. It is a read-only projection: it does not edit or execute a Recipe and does not replace Foundry's validators. See [viewer documentation](viewer/README.md) and [ADR-028](docs/decisions/028-read-only-recipe-viewer.md).

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

The Validation Report is a separate evidence object. Implementations are registered separately from Capability contracts.

## Development principles

- Contracts precede implementations.
- A schema-valid object is not necessarily semantically valid.
- Execution is deterministic where the Capability permits it and always auditable.
- Every Run records the exact versions and inputs it used, and its provenance cannot be rewritten during lifecycle transitions.
- Workers are replaceable, but must conform to a shared execution contract.
- Capability implementations must pass conformance tests before being treated as interchangeable.
- The planner is optional and never required by the execution core.
- Security, provenance, licensing, and cost visibility are architectural concerns.

## First capability: vector.buffer

`vector.buffer@1.0.0` supports Point, MultiPoint, LineString, MultiLineString, Polygon and MultiPolygon inputs. It requires an explicit projected measurement CRS equal to the input CRS, rejects invalid input geometries rather than repairing them, and returns valid Polygon/MultiPolygon outputs while preserving feature IDs and properties. Its first two independent realizations are Shapely and PostGIS; both use the same semantic request validator. The PostGIS adapter requires an unambiguous EPSG CRS and checks the output SRID. Both implementations passed the shared geometry conformance suite in [CI run 173](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/42486888151). That conformance claim is limited to the declared contract and tested cases/tolerances; it does not imply byte-identical geometry encodings.

Install the Shapely backend with the `shapely` extra or the PostGIS backend with the `postgis` extra. The PostGIS adapter does not import or require Shapely. Development installs both extras through `requirements-dev.txt`.

## Canonical runtime data

Canonical JSON Schemas, Capability contracts, and implementation manifests are packaged under `share/tessellatum-foundry/`. The runtime resolves them from the source checkout during development or from the Python installation data prefix when installed as a distribution. CI verifies this through an isolated non-editable install.

## Versioned definitions

Geo-Cells and Recipes are stored separately from Artifacts in an immutable, schema-validated definition store. A definition ID/version cannot be overwritten with different content or creator provenance. Each record carries a SHA-256 integrity checksum. The Recipe runner can resolve a registered Recipe and its exact Cell and Capability versions without accepting caller-modified contract semantics.

## Local execution

The single-cell execution service accepts one exact vector.buffer Geo-Cell version with one immutable vector Artifact input. It snapshots the exact Capability and cell versions, Artifact checksum, normalized parameters, implementation manifest checksum, worker and runtime image ID. Shapely executes in a network-disabled, read-only-root, non-root Docker container with resource and file-size limits. The control plane resolves the exact canonical Capability contract and worker implementation manifest, requiring passed conformance for that Capability version. Each Run snapshots the canonical manifest checksum separately from the immutable runtime image ID. It validates the input request and Artifact geometry metadata before dispatch; the worker repeats request validation, and the host independently validates the result before registering an immutable output Artifact.

The sequential Recipe runner composes vector.buffer cells in deterministic topological order. It resolves each downstream cell-output binding to the actual Artifact produced by the upstream Run, records the source Run and output port in the downstream input snapshot, and pins one immutable runtime image digest across the Recipe execution. Failed nodes stop downstream scheduling without rewriting successful upstream Runs. General multi-capability, parallel and remote execution remain future work. See [ADR-018](docs/decisions/018-first-local-run-and-isolated-worker.md), [ADR-022](docs/decisions/022-sequential-recipe-execution.md), and [ADR-024](docs/decisions/024-versioned-definition-storage.md).

## Scope boundary

This repository is Tessellatum Foundry. It is an independent project with its own architecture, implementation, and lifecycle.
