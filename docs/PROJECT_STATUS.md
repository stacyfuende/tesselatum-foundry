# Project status and collaboration guide

**Last updated:** 2026-11-22  
**Status:** Living engineering tracker. Update this document when a capability, validation gate, PR dependency, or operational assumption changes.

This page is the working hand-off for contributors and future sessions. It separates implemented behavior from work that is merely proposed, in review, or not yet verified. A checked implementation item does not imply that its current branch has passed CI or is production-ready. Read [Project vision](PROJECT_VISION.md) for the broader product ambition; this tracker remains the source of truth for implementation status.

## Project intent

Tessellatum Foundry is the engineering foundation for unified infrastructure for spatial data. Its responsibilities include persistent geographic identity, source-backed observations, versioned spatial representations, relationships, provenance, temporal history, spatial querying, and governed computation. The existing contracts-first computation platform remains a core subsystem.

## Spatial information core — initial implementation proposal

The reorientation branch introduces the first database model in [SPATIAL_INFORMATION_MODEL.md](SPATIAL_INFORMATION_MODEL.md), [ADR-045](decisions/045-spatial-information-core.md), and [migration 0001](../db/migrations/0001_spatial_information_core.sql).

| Component | Current state | Qualification / next step |
|---|---|---|
| Entity identity | SQL table proposed | Validate UUID identity and entity type semantics against road-network cases |
| Source registration and snapshots | Migrations 0001/0002 present; object URI/version and checksum fields added | Runtime-verify migrations; implement object download, manifest publication, and retention policy |
| Source records | Inline payload or object locator supported by migration 0002 | Implement format-aware feature locators and bounded batch ingestion |
| Source-to-entity crosswalk | SQL table proposed | Design reconciliation states and split/merge handling |
| Observations | SQL table proposed | Review temporal semantics and source/user-authored provenance |
| Spatial representations | PostGIS geometry table and GiST index proposed | Test mixed SRIDs, dimensionality, geometry types, and version lineage |
| Entity relationships | Typed directed table proposed | Define road topology conventions and validation rules |
| Python repository | Initial optional psycopg adapter added for core writes and entity lookup | Runtime-test against PostGIS; add query/history APIs and ingestion service boundary |
| Runtime verification | Not run | Apply migration to disposable PostgreSQL/PostGIS and test constraints/indexes |

**Important:** the migration is not yet runtime-verified. Do not apply it to production or claim that the information core is operational. It is additive and does not alter existing filesystem Artifact, definition, or Run stores.

## Large geospatial data architecture

[ADR-046](decisions/046-bulk-geospatial-storage.md) and [STORAGE_AND_PROCESSING_ARCHITECTURE.md](STORAGE_AND_PROCESSING_ARCHITECTURE.md) establish the bulk-data boundary. Migration 0002 and the Python adapter now support snapshot object references and source-record locators. This is schema/repository groundwork only: object upload/download, immutable manifest publication, bounded streaming ingestion, COPY-based staging, resumable checkpoints, and large-data benchmarks are not implemented yet.

| Concern | Current state | Next evidence |
|---|---|---|
| Bulk object identity | Migration 0002 adds snapshot object URI/version/format | Verify migration on disposable PostGIS |
| Source feature locator | Source record supports compact JSON or object locator | Test real GeoParquet/other reader locators |
| Storage formats | Workload-specific formats documented | Select formats from actual road/raster/point-cloud use cases |
| Streaming ingestion | Architecture specified, not implemented | Build bounded reader and retry-safe batch runner |
| Database bulk load | Not implemented | COPY-based staging and set-based merge |
| Scale validation | No large-data benchmarks | Benchmark regional/national road-network slices |

## Existing computation principles

- Capability contracts are canonical and engine-independent; implementations are registered separately.
- Schema validity is not semantic validity or methodological suitability.
- Runs snapshot exact inputs, versions, implementation identity, and provenance.
- Outputs are independently inspected before immutable Artifact registration or cache reuse.
- Fail closed on invalid CRS, geometry, band selection, non-finite data, and unverifiable claims.
- Keep local execution and remote transport boundaries explicit; do not imply a deployment is production-hardened because code exists.

## Current capability and platform inventory

| Area | Implemented / evidenced | Remaining / qualification |
|---|---|---|
| Contracts and registries | JSON Schema validation, semantic Recipe graph validation, canonical Capability registry, conformance-gated implementation registry | Continue contract evolution and installed-package checks for every new capability |
| Vector buffer | Shapely and PostGIS realizations; shared conformance; dedicated Run path and isolated local Docker worker | Broader CRS/geometry edge-case coverage; suitability and authoritative rights/security policy remain outside current evidence |
| Vector reprojection | Shapely/pyproj kernel; dedicated Run path and worker; independent output critic; mixed Recipe use; target-CRS-aware evidence-gated cache | Area-of-use review is proposed in PR #20; not a positional-accuracy guarantee |
| Recipe execution | Deterministic sequential topological execution; upstream Artifact and Run lineage; mixed buffer/reproject Recipe coverage | Parallel scheduling, retries/resume policy, and broader capability families |
| Local SDK | LocalFoundry facade over canonical registries/stores and sequential Recipe execution | Authenticated network API, multi-tenant service boundary, generated client SDK |
| Raster band statistics | Initial kernel, contract, Rasterio/NumPy packaging, independent critic, and generated GeoTIFF tests are proposed in PR #21 | Not yet integrated into Run/Artifact/Recipe lifecycle; CI verification remains outstanding |
| Remote worker | Authenticated HTTPS transport and service exist for vector capabilities | PR #13 concurrency bound and PR #15 process-isolated hard timeouts are open; production ingress, resource policy, monitoring, secret rotation and deployment verification remain |
| Provenance / methodology | Rights declarations and lineage are recorded; buffer approximation and reprojection operation evidence are recorded | Declarations are not proof of legal permission; suitability, authoritative rights policy, security policy and accuracy assessment require additional inputs and governance |

## Verification and release discipline

For every PR, record:
- exact head commit SHA;
- required GitHub Actions checks and their final states;
- unit, conformance, integration, Docker/PostGIS and packaging coverage as applicable;
- whether tests were run locally or only in CI;
- known limitations and any manual deployment checks still outstanding.

Do not equate an empty status list with success. Do not claim a CI pass without a completed successful check on the current head SHA. Re-run checks after any commit that changes source, tests, schemas, manifests, or packaging.

## Suggested collaboration workflow

1. Start with this page, [the architecture](../ARCHITECTURE.md), and the [decision register](decisions/README.md).
2. Read the relevant ADR and Capability contract before changing behavior.
3. Keep each PR scoped to one capability or infrastructure concern; state dependencies and non-goals in its description.
4. Add tests at contract, kernel, independent-critic, lifecycle, and packaging boundaries as relevant.
5. Update this tracker in the same PR when status, dependencies, semantics, or next steps change.
6. Preserve explicit not_run / unverified states until conformance and runtime evidence justify promotion.

## Decision and evidence index

- [ADR-045](decisions/045-spatial-information-core.md): persistent spatial information core (this reorientation PR).
- [ADR-043](decisions/043-reprojection-area-of-use-coverage.md): reprojection area-of-use coverage.
- [ADR-044](decisions/044-raster-band-statistics.md): raster band statistics scope and semantics.
- [ADR-039](decisions/039-methodological-evidence.md), [ADR-040](decisions/040-buffer-arc-approximation.md), [ADR-041](decisions/041-buffer-arc-tolerance.md), [ADR-042](decisions/042-reprojection-operation-evidence.md): methodology and operation evidence.
- [ADR-032](decisions/032-authenticated-remote-worker-transport.md) and [ADR-036](decisions/036-remote-vector-capability-dispatch.md): remote transport and capability dispatch.

---
*This document is intentionally a living tracker, not a substitute for immutable ADRs, PR descriptions, test results, or release records.*
