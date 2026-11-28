# Project status and collaboration guide

**Last updated:** 2026-11-28  
**Status:** Living engineering tracker.

This page distinguishes implemented behavior from proposed work and unverified assumptions. A checked item does not imply production readiness. Read [Foundry architecture](FOUNDRY_REORIENTATION.md) and [Project vision](PROJECT_VISION.md) for current direction.

## Project intent

Foundry is Tessellatum's spatial computation infrastructure. It makes spatial data computable across providers, formats, engines, workflows and applications. It does not aim to own or permanently host source datasets by default.

## Current computational foundation

| Area | Implemented / evidenced | Remaining / qualification |
|---|---|---|
| Contracts and registries | JSON Schema validation, semantic Recipe graph validation, canonical Capability registry, conformance-gated implementation registry | Continue contract evolution and installed-package checks |
| Spatial validation | CRS, geometry, extent and measurement-unit checks | Expand source metadata validation and method-specific evidence |
| Vector buffer | Shapely and PostGIS realizations; shared conformance; dedicated Run path and isolated local Docker worker | Broader edge cases; suitability and rights policy remain distinct |
| Vector reprojection | Shapely/pyproj kernel; dedicated Run path and worker; independent output critic; mixed Recipe use; evidence-gated cache | Area-of-use review and accuracy limits remain explicit |
| Recipe execution | Deterministic sequential execution, upstream Artifact/Run lineage, mixed buffer/reproject Recipe coverage | Parallel scheduling, robust retries/resume and broader capability families |
| Local SDK | LocalFoundry composition root over canonical stores and execution services | Authenticated network API, multi-tenant service boundary, generated client SDK |
| Raster band statistics | Initial kernel, contract, Rasterio/NumPy packaging, independent critic and generated GeoTIFF tests proposed in PR #21 | Integrate into Run/Artifact/Recipe lifecycle and verify CI |
| Remote worker | Authenticated HTTPS transport and service exist for vector capabilities | Concurrency, process-isolated hard timeouts, ingress, resource policy, monitoring, secret rotation and deployment verification |
| Provenance and methodology | Rights declarations and lineage; buffer approximation and reprojection operation evidence | Declarations are not legal authorization; suitability and accuracy need domain evidence |

## Outcome-first Product Factory — implemented foundation, not a shipped product

| Component | Implemented / evidenced | Remaining / qualification |
|---|---|---|
| Product Blueprint contract | Outcome, audience, evidence requirements, reasoning nodes, outputs, acceptance, autonomy and resource limits are declarative and schema-bound | Source discovery/resolution UX, rights/freshness/quality assessment |
| Blueprint planner | Deterministic dependency ordering, exact registered Capability resolution, evidence and output-port checks, policy-sensitive plan fingerprint | Planning interface and interactive assumption resolution |
| Guarded compilation | Blueprint plan compiles to schema-valid immutable Geo-Cells and Recipe; exact upstream port bindings; resolved inputs must be typed Artifact/external references; complete output contracts required | Data binding and template selection are still explicit runtime inputs |
| Execution handoff | Re-plans against current registry/policy, rejects stale plan and non-automatic decisions, persists definitions, reuses registered Recipe Run service | Real customer-input product factory run not yet demonstrated |
| Product acceptance | Registered Run, output, Artifact metadata and checksum validators; unknown validators remain unassessed and block release | Geometry validity, methodological suitability, source rights, freshness, cartographic/UX quality and monitoring validators |
| Product manifest | Deterministic assembled manifest with product output inventory, Artifact metadata, execution and Run provenance, acceptance and fingerprint | No public/customer delivery, product renderer, release, deployment or operations service |
| Example Blueprint | Road-access buffer example for a 500m access zone | Requires a real input Artifact and actual registered worker execution to prove end-to-end |

**Honest proof boundary:** the Blueprint-to-acceptance-manifest test exercises the orchestration using test doubles. It is not a live worker run. The external Sentinel-2 raster-window proof remains separate evidence for the real-source raster path.

## Customer-language product request intake — first supported job

| Component | Implemented / evidenced | Remaining / qualification |
|---|---|---|
| Customer request contract | Versioned customer-language request schema covering the job, source file, CRS, audience, decision context and supported geography; no capability or Recipe vocabulary | Expand only when another validated customer job is added |
| Customer interface | Browser composer inspects a GeoJSON Point FeatureCollection locally, checks bounded Nairobi scope, gathers context and supports an explicit authenticated submission | Real deployed browser-to-hosted-API journey still needs verification |
| Deterministic resolver and ingestion | Approved packaged Nairobi template; bounded source ingestion; immutable Artifact registration; exact registered capability planning; rejects unsupported job, CRS, geography, path and media-type mismatch | No free-form method generation; more approved jobs need their own templates, constraints and tests |
| Execution and delivery | Docker-backed end-to-end HTTP integration runs the authenticated request through tenant runtime, `vector.reproject@1.0.0`, acceptance, manifest and verified ZIP delivery | Hosted identity provider, durable tenant storage and production operations remain deployment work |

The customer request is deliberately not executable code. It is the boundary between a customer's job description and Foundry's internal Blueprint machinery. See [ADR-062](decisions/062-customer-language-product-request-intake.md) and [ADR-067](decisions/067-authenticated-customer-product-http-integration.md).

## External data boundary — initial source-backed execution implemented

| Concern | Implemented | Remaining / qualification |
|---|---|---|
| Source access | Provider-neutral `SourceAdapter`, bounded local-file adapter, and exact-host-allowlisted HTTPS adapter with runtime headers, no redirects, timeouts, byte/ETag/SHA-256 checks and redacted transport errors | Provider pagination/query pushdown, cloud-native signed access, OAuth refresh, DNS/IP policy and production credential broker |
| Bounded reads | Incremental NDJSON reader and lazy source-to-batch pipeline; feature-count and encoded-byte bounds | Additional readers, pagination, windowing and query pushdown |
| Batch worker | `VectorBufferBatchExecutor` verifies batch input checksum/metadata, pinned worker image, output shape/count, output checksum and worker-reported CRS; exercised by source-backed orchestration | Additional worker implementations and operational resource policy |
| Source identity | `ExternalDataReference` records provider/dataset/resource URI and optional version/ETag/SHA-256 evidence | Provider-specific stable version evidence and source-aware cache identity |
| Run provenance | Immutable source references are validated against input ports and preserved across retries; Geo-Cell schema supports explicit external bindings; `ExternalVectorBufferRunFactory` creates source-only queued Runs; `ExternalVectorBufferRunOrchestrator` authorizes, resolves, streams, dispatches, validates and finalizes source-backed Runs | Cursor/checkpoint evidence and durable retry semantics |
| Output lifecycle | Private provisional staging, atomic journal, EOF gate, bounded file-based Artifact writer, durable object-before-metadata publication, stable publication intent, conservative process-restart reconciliation, bounded Artifact integrity verification, producer Run/attempt binding, verified Run success reconciliation, bounded per-batch independent critic, aggregate report, and `ExternalVectorBufferRunOrchestrator` joining source-only queued Runs to streamed execution | Resumable checkpoints, cross-process writer lease, remote source adapters and production credential brokering remain pending |
| Credentials | Authorization is invoked before adapter resolution; provider exception text is redacted from caller-visible errors and persisted Run records; URI userinfo, query strings and fragments are rejected | Production scoped credential broker, rotation and provider-specific authorization policy |
| Source custody | Remains with provider/customer by default | Architectural rule |
| Snapshots | Optional customer-controlled snapshot, not mandatory Foundry ingestion | Policy only; no snapshot service planned as core |

## Persistence boundary

Foundry may persist:
- immutable Cell and Recipe definitions;
- Run events, provenance and validation reports;
- bounded cache metadata and entries under eviction policy;
- derived output Artifacts when required by the workflow.

Foundry does not default to persisting:
- complete upstream datasets;
- mirrored national/global geospatial catalogues;
- canonical geographic entity inventories;
- bulk input archives.

The current filesystem Artifact store is a local adapter. A future artifact backend must support explicit ownership, access and retention policy. This is distinct from a source-data warehouse.

## Decisions

- ADR-045 and ADR-046 were proposed during an earlier storage-centric interpretation and are superseded by ADR-047.
- [ADR-047](decisions/047-external-data-computation-boundary.md) records the current external-data and computation boundary.
- Existing accepted computation ADRs remain in force unless explicitly superseded.

## Verification status

CI run [#815](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/45338892077) completed successfully on the source-backed orchestration branch, including installed-package/schema checks, lint, both worker-image builds and the full Docker/PostGIS test suite. Its test job includes the opt-in Docker-backed local-source integration test, which exercises authorization, bounded source reading, worker execution, independent validation, transactional Artifact publication and successful Run reconciliation. Commit `409dbefdee5744b8648cbf4d5dd67bc8989bba35` adds a caller-visible error-redaction assertion for provider authorization failures.

This verifies the local-file adapter path and one `vector.buffer` implementation in CI. It does not establish production readiness for remote providers, credential brokering, resumable execution, distributed worker ownership or broader Capability support.

For each subsequent commit, record the exact head SHA and final checks. Do not claim a CI pass without a completed successful run on the current head.

## Collaboration workflow

1. Read the relevant Capability contract and ADR before changing behavior.
2. Preserve canonical contracts and test at schema, semantic, kernel, independent-critic, lifecycle and packaging boundaries.
3. Keep source access adapters separate from capability semantics.
4. Add tests for bounded memory, partial failures, unavailable sources, credential redaction and provenance.
5. Update this tracker when implementation status or assumptions change.
6. Keep unverified behavior explicitly unverified.


## Spatial product viewer (first customer-facing output surface)

A dependency-free browser viewer now opens GeoJSON Features and FeatureCollections locally. It provides a geometry preview, feature/coordinate counts, extent, geometry composition, per-feature properties and GeoJSON download. This is a first usable output surface, not yet a Foundry-connected product delivery path. It assumes WGS 84 longitude/latitude, has 50,000-feature / 100 MB preview limits, has no basemap or raster support, and does not certify geometry or analytical quality. The included sample is illustrative only. See `viewer/product/index.html` and `viewer/product/README.md`.


## Verified product export (first Artifact-to-customer handoff)

A GeoJSON export adapter now turns an accepted Product Manifest into a deterministic ZIP bundle. It resolves each exact Artifact ID/version through the configured Artifact Store, compares immutable Artifact metadata with the assembled manifest, reads bytes through the store's SHA-256-verifying API, validates GeoJSON payload type, enforces a configurable aggregate byte limit, and packages the source manifest, export index and GeoJSON outputs. Only `accepted` products with `release_allowed=true` can be exported. The bundle includes the accepted source manifest, the exact canonical manifest bytes used for its fingerprint, an export index and GeoJSON outputs. The browser viewer can open the extracted bundle files selected together, verify the canonical manifest fingerprint with Web Crypto, cross-check each output against its immutable Artifact reference, verify file sizes and SHA-256 checksums, and inspect each GeoJSON output. It does not upload data or fetch arbitrary URLs. ADR-061 documents the contract.

**Proof boundary:** unit tests cover bundle contents, determinism, rejected/unaccepted products, manifest tampering, Artifact metadata mismatch, invalid GeoJSON and export size limits; storage tests cover bounded reads. The viewer has static and script-syntax checks, but a real browser interaction test on the current deployed commit remains outstanding. This is a portable export adapter, not hosted publication, a signed distribution mechanism, customer access control, or a live Artifact API. It currently supports GeoJSON only; raster and other product formats need their own delivery adapters/viewers.

## Outcome-first product examples

Two distinct customer jobs now have explicit, schema-validated Spatial Product Blueprints:

- `examples/product_blueprints/road-access-buffer.json`: create a 500 m road-proximity polygon dataset for planning and site-selection analysis.
- `examples/product_blueprints/nairobi-site-coordinate-standardization.json`: convert WGS 84 site locations to EPSG:32737 for metric analysis, preserving feature identity and attributes.

The second example is deliberately a different product outcome, not another buffer variant. Its planner test verifies that the exact registered `vector.reproject@1.0.0` capability is selected with the intended source binding and target CRS. This proves planning only; it does not claim that this example has been executed and exported end-to-end. The existing Docker-backed product integration test covers the road-buffer product path.

### Real product execution coverage

The second outcome-first product now has a Docker-backed integration test that exercises the registered `vector.reproject@1.0.0` worker through the same Blueprint → Recipe → Run → Artifact → acceptance → Product Manifest → verified GeoJSON bundle path. It uses an immutable WGS 84 site Artifact, checks preservation of feature ID and properties, and checks that the exported Nairobi point falls in the expected UTM zone 37S coordinate range. This test runs in container CI using the already-built isolated Shapely worker image. The Blueprint's site dataset is a required execution input resolved to an Artifact; the separate evidence-requirement list is empty because no independent evidence reference is being asserted.



### Spatial Product Viewer CRS and geometry support

The browser viewer now takes CRS metadata from the verified export manifest's output Artifact, rather than labelling every bundled output as EPSG:4326. Direct RFC 7946 GeoJSON retains its WGS 84 default; bundles with missing CRS metadata are explicitly labelled undeclared. Projected coordinates are displayed in their native plane without reprojection or a basemap. GeometryCollections, including nested collections, are now drawn alongside the existing simple and multi-geometry types. This is display support, not a CRS transformation or GIS certification.


### Customer-facing product handoff

Product manifests now carry the customer-facing intent from the Blueprint: title, description, intended outcome, audience, decision context, geographic scope and success criteria. The local viewer renders this alongside the verified acceptance-check results and spatial output, so a customer can understand what the deliverable is for before inspecting its geometry. The handoff is populated only from the fingerprint-verified bundle manifest; it does not infer or invent product claims. Direct GeoJSON remains a generic preview. A mocked verified-bundle smoke test exercised the product brief, success criteria, acceptance statuses and EPSG:32737 label. Hosted publication, customer authentication and a signed distribution channel remain separate work.


### Point-coordinate analyst export

The product viewer now offers a CSV export for point-only datasets, in addition to the verified GeoJSON handoff. It includes feature identifiers, X/Y values, the active CRS label and a stable union of feature-property columns. It deliberately disables this export for non-point geometries rather than silently substituting centroids or dropping geometry detail. Text values that could be interpreted as spreadsheet formulas are escaped. This is a convenience export from the already-opened local dataset, not a new server-side artifact or replacement for the original GeoJSON.


### Customer request composer and authenticated submission

The customer page now inspects a selected GeoJSON Point FeatureCollection locally, enforces the bounded Nairobi intake envelope, collects audience and decision context, and prepares the supported product request. It also provides an explicit authenticated submit flow: the operator-approved HTTPS API endpoint and bearer token are entered at submission time; the token remains in page memory and is cleared on page hide/reset; the source file is transmitted only after the user confirms authorization. A verified ZIP is downloaded only when the API returns an accepted, releasable product. A request-JSON download remains available as a fallback. This is still a pilot intake page; a current-commit browser interaction test and deployed customer journey are outstanding.

## Authenticated customer API and local tenant runtime

The authenticated `POST /v1/products` adapter accepts a versioned JSON envelope, authenticates before resolving tenant runtime, enforces request/source size bounds, uses exact-origin CORS, and returns a ZIP only after product acceptance and release checks. `LocalTenantRuntimeResolver` creates one `LocalFoundry` composition per trusted tenant identity, with separate local Artifact, Run, definition, Capability and Recipe-service instances. It installs only the reviewed site-coordinate-standardization template; customers cannot supply execution code or runtime configuration.

**Verification:** [CI run #46133161084](https://github.com/stacyfuende/tesselatum-foundry/actions/runs/46133161084) passed on commit `053e69737b58096351cd01209aae72f50099e297`: 562 passed, 2 skipped (optional live-STAC environment not configured), 1 warning. Both worker images built, Docker/PostGIS tests passed, the customer-page control and JavaScript checks passed, and the independent live Nairobi Sentinel-2 raster execution passed.

**Boundary:** the tenant runtime remains a single-host local adapter, not production multi-tenant hosting. Process-local caching and local filesystem stores do not provide distributed coordination, object-store IAM isolation, encryption, backup/retention, TLS, identity-provider integration, rate limiting or operational monitoring. No production API hostname or credentials are configured. See [ADR-066](decisions/066-local-tenant-runtime-isolation.md) and the [Customer Product API deployment guide](customer-product-api-deployment.md).
