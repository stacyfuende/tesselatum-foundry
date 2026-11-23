# Project status and collaboration guide

**Last updated:** 2026-11-23  
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

## External data boundary — implementation in progress

| Concern | Implemented | Remaining / qualification |
|---|---|---|
| Source access | Provider-neutral `SourceAdapter` protocol and bounded local-file adapter | Remote/provider adapters and runtime authorization |
| Bounded reads | Incremental NDJSON reader and lazy source-to-batch pipeline; feature-count and encoded-byte bounds | Additional readers, pagination, windowing and query pushdown |
| Batch worker | `VectorBufferBatchExecutor` verifies batch input checksum/metadata, pinned worker image, output shape/count and output checksum | Not yet integrated with Run orchestration or whole-run validation |
| Source identity | `ExternalDataReference` records provider/dataset/resource URI and optional version/ETag/SHA-256 evidence | Provider-specific stable version evidence and source-aware cache identity |
| Run provenance | Immutable source references are validated against input ports and preserved across retries | Direct external input execution and cursor/checkpoint evidence |
| Output lifecycle | Existing Artifact store remains immutable and content-addressed | Streaming writer, provisional output staging, atomic finalization and cleanup on failure |
| Credentials | Source references reject URI userinfo, query strings and fragments | Scoped runtime credential injection and authorization policy |
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

PR #24 CI run #718 passed on commit `751f248dbff5fe72d3883d5c8e71c12846b67f20`, including installed-package/schema checks, lint, both worker-image builds and the full Docker/PostGIS test suite. The subsequent batch-worker adapter and its tests are newer commits and require a fresh CI run.

For each subsequent commit, record the exact head SHA and final checks. Do not claim a CI pass without a completed successful run on the current head.

## Collaboration workflow

1. Read the relevant Capability contract and ADR before changing behavior.
2. Preserve canonical contracts and test at schema, semantic, kernel, independent-critic, lifecycle and packaging boundaries.
3. Keep source access adapters separate from capability semantics.
4. Add tests for bounded memory, partial failures, unavailable sources, credential redaction and provenance.
5. Update this tracker when implementation status or assumptions change.
6. Keep unverified behavior explicitly unverified.
