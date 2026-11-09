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
- [~] Local `foundry` operator CLI supports workspace initialization, Artifact ingest/export, immutable Cell/Recipe registration, Recipe execution, and Run/report/registry inspection; it is a local single-user interface, not a hosted API.
- [~] Optional FastAPI control plane provides bearer-authenticated Artifact, definition, Recipe execution, Run, report, and registry endpoints with a non-root container image; it is single-tenant/private-preview infrastructure, not production multi-tenant hosting.
- [~] Execution/output validation and operation-specific methodological evidence are implemented for vector.buffer and vector.reproject. Rights provenance evidence records declarations and lineage without inferring permission. Analytical suitability, area-of-use/accuracy review, and authoritative rights/security policy evaluation remain outstanding.
- [~] Recipe orchestration dispatches through exact capability-version runner registrations. vector.buffer@1.0.0 and vector.reproject@1.0.0 now have separate Run services and isolated local Docker workers; a mixed-capability sequential Recipe is integration-tested. Parallel scheduling remains outstanding.
- [~] Authenticated HTTPS remote worker adapter and HTTP execution service implemented; deployment hardening and end-to-end remote Run conformance remain outstanding.
- [~] First raster kernel and canonical contract introduced: raster.band_statistics@1.0.0 computes exhaustive per-band statistics over valid finite stored samples. Run/Recipe integration and conformance CI remain outstanding.
- [x] Dependency-free read-only Recipe DAG viewer implemented.
- [x] Deterministic execution cache with immutable output reuse and parameter-based invalidation implemented; cache reuse requires current complete output-validation evidence.
- [~] Local Python SDK, authenticated single-tenant control-plane API, dependency-free Python API client, and browser Console are implemented for a restricted private preview; user identities, roles, tenant isolation, durable database/object storage, and a generated SDK remain outstanding.

Items are marked complete when implementation and corresponding tests are present. Runtime and CI verification are reported separately.

## Launch readiness

See the [launch plan](docs/LAUNCH_PLAN.md) for the private-preview verification gates and the separate requirements for a public multi-tenant release. The presence of an API, client, Console, or container image does not mean the service is production-ready.

## Browser operator console

A static, same-origin Console now provides a browser workflow for Artifact intake, Cell/Recipe registration, execution, Run/report inspection, and checksum-verified output downloads. See [deploy/console](deploy/console/README.md). It is designed for the private single-tenant preview and uses the control-plane API; it is not a multi-user workflow designer.

## Private control-plane API

An optional FastAPI service provides bearer-authenticated Artifact, Cell, Recipe, Run, Validation Report, and registry endpoints. Build and deployment instructions are in [deploy/control-plane](deploy/control-plane/README.md). This is a controlled single-tenant private-preview boundary; it is not production multi-tenant hosting.

## End-to-end quickstart

A runnable synthetic-data example demonstrates Artifact ingestion, immutable Cell/Recipe registration, isolated Docker execution, output validation, and checksum-verified export. Follow [examples/quickstart](examples/quickstart/README.md) to execute the first vector.buffer Recipe locally.

## Local operator CLI

Install from a source checkout with `python -m pip install -e '.[shapely]'`, then initialize a workspace:

```bash
foundry --data-dir ./foundry-data init
```

The CLI can ingest checksum-addressed Artifacts, register immutable Cell and Recipe definitions, execute a registered Recipe through the isolated Docker workers, inspect Runs and Validation Reports, and export checksum-verified Artifact bytes. See the [operator CLI guide](docs/CLI.md) for the complete workflow and its local-only deployment boundary.

## Python SDK

The local SDK is the first convenience interface over the canonical contracts. It registers exact runners for both vector.buffer and vector.reproject; install the Shapely extra for host-side output validation, then use an explicit persistent directory. Each capability executes through its isolated Docker worker by default:

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

Pass `reproject_worker` to `LocalFoundry` to override the default reprojection worker; the original `worker` argument remains the vector.buffer worker for compatibility. The facade also exposes `store_artifact`, `get_run`, `list_recipe_runs`, `get_artifact`, `get_validation_report`, and `read_artifact`. The latter verifies the Artifact checksum. This is a local SDK, not an authenticated network API or multi-tenant service. See [ADR-025](docs/decisions/025-local-python-sdk.md).

## Read-only Recipe viewer

Open [viewer/index.html](viewer/index.html) in a browser, then paste a canonical Recipe JSON document or select it from disk. The viewer renders exact Geo-Cell references, directed port dependencies, topological depth, and declared outputs. It is a read-only projection: it does not edit or execute a Recipe and does not replace Foundry's validators. See [viewer documentation](viewer/README.md) and [ADR-028](docs/decisions/028-read-only-recipe-viewer.md).

## Start here

1. [Project vision](docs/PROJECT_VISION.md) — the long-term Tessellatum ambition and how Foundry contributes to it.
2. [Living project status and collaboration guide](docs/PROJECT_STATUS.md) — current implementation, open work, verification gates, and hand-off notes.
3. [Architecture](ARCHITECTURE.md)
4. [Decision register](docs/decisions/README.md)
5. [Schemas](schema/)
6. [v0.1 acceptance criteria](tests/acceptance/README.md)

## Foundational model

1. **Artifact** — a versioned data object.
2. **Capability** — a versioned contract describing an operation.
3. **Geo-Cell** — a declarative, versioned instance of a computation.
4. **Run** — one attempt to execute a Geo-Cell.
5. **Recipe** — a versioned graph composing Geo-Cells.

The Validation Report is a separate evidence object. Implementations are registered separately from Capability contracts. Rights declarations are preserved through vector transformations and linked to their source Artifact; a recorded licence is not treated as proof of permission. See [ADR-038](docs/decisions/038-rights-provenance-evidence.md). Methodological reports distinguish enforceable operation semantics from suitability questions that require analytical purpose, area of interest, and accuracy tolerance. Buffer reports also quantify the radial approximation error implied by `quad_segs`, record cap/join semantics, and compare that error with an optional Cell-declared `buffer_arc_tolerance`. Reprojection reports capture the worker-reported PROJ operation, pipeline definition, accuracy, and area of use from the pinned runtime that performed the transformation; these are execution records, not independent cryptographic attestations. See [ADR-039](docs/decisions/039-methodological-evidence.md), [ADR-040](docs/decisions/040-buffer-arc-approximation.md), [ADR-041](docs/decisions/041-buffer-arc-tolerance.md), and [ADR-042](docs/decisions/042-reprojection-operation-evidence.md). Methodological reports distinguish enforceable operation semantics from suitability questions that require analytical purpose, area of interest, and accuracy tolerance. See [ADR-039](docs/decisions/039-methodological-evidence.md).

## Development principles

- Contracts precede implementations.
- A schema-valid object is not necessarily semantically valid.
- Execution is deterministic where the Capability permits it and always auditable.
- Every Run records the exact versions and inputs it used, and its provenance cannot be rewritten during lifecycle transitions.
- Workers are replaceable, but must conform to a shared execution contract.
- Capability implementations must pass conformance tests before being treated as interchangeable.
- The planner is optional and never required by the execution core.
- Security, provenance, licensing, and cost visibility are architectural concerns.

## Vector capabilities

`vector.reproject@1.0.0` is the second registered vector operation. Its Shapely/pyproj kernel accepts an explicit source CRS from Artifact metadata and an explicit target CRS parameter, uses x/y axis order, rejects ballpark coordinate operations, preserves feature IDs/properties and geometry types, and fails closed on invalid or non-finite geometries. It deliberately does not repair geometry, densify edges, clip, or split antimeridian crossings. Its contract and kernel pass the registered conformance suite in [CI run 502](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/42509028218). It now has a dedicated Run service, local Docker worker, and independent output critic; mixed-capability sequential Recipe execution is tested. It uses the shared spatial output critic 0.2.0 and can reuse deterministic outputs only when the source Run's complete validation evidence, target-CRS invariant, Artifact metadata, rights, and checksum all pass cache checks. See [ADR-033](docs/decisions/033-vector-reproject-crs-semantics.md), [ADR-035](docs/decisions/035-vector-reproject-run-integration.md), and [ADR-037](docs/decisions/037-reprojection-cache-evidence.md).

## First capability: vector.buffer

`vector.buffer@1.0.0` supports Point, MultiPoint, LineString, MultiLineString, Polygon and MultiPolygon inputs. It requires an explicit projected measurement CRS equal to the input CRS, rejects invalid input geometries rather than repairing them, and returns valid Polygon/MultiPolygon outputs while preserving feature IDs and properties. Its first two independent realizations are Shapely and PostGIS; both use the same semantic request validator. The PostGIS adapter requires an unambiguous EPSG CRS and checks the output SRID. Both implementations passed the shared geometry conformance suite in [CI run 173](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/42486888151). That conformance claim is limited to the declared contract and tested cases/tolerances; it does not imply byte-identical geometry encodings.

Install the Shapely backend with the `shapely` extra or the PostGIS backend with the `postgis` extra. The PostGIS adapter does not import or require Shapely. Install raster support with the `raster` extra. Development installs all three optional backends through `requirements-dev.txt`.

## Canonical runtime data

Canonical JSON Schemas, Capability contracts, and implementation manifests are packaged under `share/tessellatum-foundry/`. The runtime resolves them from the source checkout during development or from the Python installation data prefix when installed as a distribution. CI verifies this through an isolated non-editable install.

## Versioned definitions

Geo-Cells and Recipes are stored separately from Artifacts in an immutable, schema-validated definition store. A definition ID/version cannot be overwritten with different content or creator provenance. Each record carries a SHA-256 integrity checksum. The Recipe runner can resolve a registered Recipe and its exact Cell and Capability versions without accepting caller-modified contract semantics.

## Local execution

The single-cell execution services accept exact vector.buffer and vector.reproject Geo-Cell versions with immutable vector Artifact inputs. Each Run snapshots the exact Capability and Cell versions, Artifact checksum, normalized parameters, implementation manifest checksum, worker identity, and runtime image ID. Both operations execute in a network-disabled, read-only-root, non-root Docker container with resource and file-size limits. The control plane resolves the exact canonical Capability contract and worker implementation manifest, requiring passed conformance for that Capability version. Each Run snapshots the canonical manifest checksum separately from the immutable runtime image ID. It validates the input Artifact and capability-specific spatial preconditions before dispatch; the worker repeats request validation, and the host independently validates the result before registering an immutable output Artifact. Reprojection requires the Cell's declared target CRS to match its output contract. Its deterministic cache key includes the target CRS, exact implementation manifest checksum, runtime image digest, and shared output-critic version; cache reuse requires the target-CRS finding and complete source validation evidence.

The sequential Recipe runner composes vector.buffer and vector.reproject cells in deterministic topological order. A mixed Recipe that reprojects WGS84 point data to UTM 37S and then buffers it is covered by Docker/PostGIS CI. It resolves each downstream cell-output binding to the actual Artifact produced by the upstream Run, records the source Run and output port in the downstream input snapshot, and pins the exact runtime image digest independently for each capability runner used by the Recipe. Failed nodes stop downstream scheduling without rewriting successful upstream Runs. General parallel scheduling and additional capability families remain future work. Authenticated HTTP adapters and a matching remote spatial worker service support vector.buffer and vector.reproject behind a trusted TLS ingress. Build the service image with `docker build -f workers/vector_buffer/Dockerfile.remote -t foundry-spatial-worker-remote .`; the original local Dockerfile and CLI entrypoint remain unchanged. By default the service advertises vector.buffer@1.0.0. To deploy reprojection instead, configure `FOUNDRY_WORKER_CAPABILITY_ID=vector.reproject`, `FOUNDRY_WORKER_CAPABILITY_VERSION=1.0.0`, and `FOUNDRY_IMPLEMENTATION_ID=vector-reproject-pyproj-shapely`. Each process advertises and executes exactly one capability version. The service requires a bearer token and an explicitly configured immutable runtime image digest; it rejects unauthenticated requests, unsupported capability versions, oversized bodies, and redirects. Keep it on a private network, terminate TLS at a trusted ingress, and apply container CPU, memory, process, and network policies at deployment. The remote adapters refuse plain HTTP except for explicit localhost tests. Remote transport is not yet a production multi-tenant API. See [ADR-018](docs/decisions/018-first-local-run-and-isolated-worker.md), [ADR-022](docs/decisions/022-sequential-recipe-execution.md), [ADR-024](docs/decisions/024-versioned-definition-storage.md), [ADR-032](docs/decisions/032-authenticated-remote-worker-transport.md), and [ADR-036](docs/decisions/036-remote-vector-capability-dispatch.md).

## Scope boundary

This repository is Tessellatum Foundry. It is an independent project with its own architecture, implementation, and lifecycle.
