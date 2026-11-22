# Storage and processing architecture for large geospatial data

**Status:** Proposed engineering constraint for Foundry 0.1+  
**Decision:** [ADR-046](decisions/046-bulk-geospatial-storage.md)  
**Schema change:** [Migration 0002](../db/migrations/0002_bulk_object_storage_boundary.sql)

## Core rule

**Do not make PostgreSQL carry the bulk bytes simply because it is convenient to query.** Foundry separates bulk-data durability from the spatial information index. Data volume can grow independently of the relational database.

## Three cooperating planes

| Plane | Responsibility | Typical contents |
|---|---|---|
| Object/data plane | Durable, immutable bulk bytes | Original source archives, GeoParquet, COG, COPC/LAZ, tiled datasets, large derived artifacts |
| Information plane | Identity, provenance, temporal assertions, relationships, operational spatial lookup | Entities, source snapshots, record locators, observations, selected geometries, topology, GiST indexes |
| Compute plane | Bounded, reproducible transformation and validation | Streaming readers, chunk transforms, staging/COPY, workers, Recipes/Runs, validation evidence |

These planes are logically separate even if early deployment runs them in one region/account.

## Data lifecycle

1. **Capture:** stream provider bytes to a temporary object key while computing SHA-256 and byte count. Do not load the entire file into memory.
2. **Seal:** finalize an immutable object version and write a snapshot manifest containing source identity, required SHA-256 checksum, size, media type, format, CRS declarations, time range, and license/rights declarations.
3. **Register:** create the source snapshot record with its durable object URI/version. A snapshot is not considered available until its object checksum has been verified.
4. **Inspect:** read metadata and sample/scan the source using streaming/windowed readers. Record schema, CRS, geometry type, extent, counts where available, and inspection evidence.
5. **Transform:** process bounded features/tiles/windows. Write curated partitions to temporary object keys; never accumulate an entire national extract in RAM.
6. **Index:** stage compact entity/source/link/observation rows in batches. Use COPY for bulk staging, then transactional set-based reconciliation into serving tables. Avoid one INSERT round-trip per feature for national-scale loads.
7. **Publish:** verify output objects and database batch counts/checksums, then atomically mark the import manifest/batch published. Failed imports leave recoverable staged objects and do not masquerade as complete snapshots.
8. **Query/export:** route interactive entity and local spatial queries to PostGIS; route broad scans and large analytical operations to partitioned object datasets and appropriate compute engines. Export exact object versions and database snapshot identifiers together.

## Storage formats are workload choices

- **Vector analytical data:** GeoParquet/Parquet with partitioning chosen for access patterns (often region or spatial tile plus time), statistics, and row-group sizing.
- **Raster:** Cloud Optimized GeoTIFF for windowed/range access; retain original source bytes as well.
- **Point clouds:** COPC/LAZ where supported by the source and use case.
- **Distribution tiles:** PMTiles or a tiled object layout for read-heavy map delivery.
- **Operational features/topology:** PostGIS for entity-scale spatial filtering, relationship queries, and transactional updates.

Do not convert away the original source. Curated representations are derived products with their own checksums, formats, lineage, and version identity.

## PostgreSQL/PostGIS responsibilities

PostGIS stores durable IDs and the minimum spatial representation needed to answer operational questions: locate an entity, find nearby/overlapping candidates, traverse network relationships, inspect history, and reconcile source records.

It does not need a duplicate copy of every source archive, raster pixel, point return, tile, or intermediate. Large feature bodies can be referenced through source-record locators into immutable snapshot/curated objects. The object locator is not itself an entity ID.

Keep initial deployment simple: one PostgreSQL/PostGIS service and an object store. Add table partitioning, read replicas, analytical query engines, or distributed storage only after representative benchmarks demonstrate a bottleneck. Avoid sharding stable entity identity prematurely.

## Bounded, restartable ingestion

An import is a sequence of bounded batches, not one giant transaction:
- each batch has a deterministic import/batch key and source range or partition identity;
- batch size is configurable by byte budget and feature count;
- memory is bounded by the reader window, transform buffers, and in-flight output buffers;
- every output object is checksum-verified before publication;
- database staging uses COPY or equivalent bulk paths;
- retries reuse stable batch IDs and verify already-written outputs rather than duplicate them;
- checkpoints record source locator/range, output object versions, counts, checksums, and validation result;
- the final publication step is idempotent and only exposes complete outputs.

A single huge database transaction is not the scaling strategy. Batch-level atomicity plus a final publication manifest is.

## Capacity and cost discipline

The architecture is not constrained to free tiers. Choose storage and compute based on workload, durability, residency, egress, and operator requirements. Cost must be measured across:
- object storage capacity, requests, lifecycle/versioning, replication, and egress;
- database storage, IOPS, CPU, memory, index size, WAL, replicas, and backups;
- worker CPU/RAM, temporary disk, network, and concurrency;
- analytical scans, caching, and data movement.

Set explicit workload budgets and service objectives, not a free-tier ceiling. Keep providers replaceable through interfaces and standard formats, but do not pretend cloud services are interchangeable without testing.

## Current implementation boundary

Migration 0002 creates the initial source snapshot object reference and source record locator fields. The Python repository adapter can register these references. A bounded-memory S3-compatible streaming uploader now supports single-part and multipart uploads with SHA-256 receipts; it accepts an injected client and leaves credentials/policy to the deployment. Object download, manifest publication, batch staging/COPY, orchestration, and end-to-end large-data benchmarks remain subsequent work.
