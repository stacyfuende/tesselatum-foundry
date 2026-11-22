# ADR-046: Separate bulk geospatial bytes from the PostGIS information index

**Status:** Proposed  
**Date:** 2026-11-22  
**Related:** ADR-045, `SPATIAL_INFORMATION_MODEL.md`, migrations 0001 and 0002

## Context

Foundry is intended to support national and potentially much larger geospatial datasets. Raw vector extracts, rasters, point clouds, imagery, meshes, simulation outputs, and derived analytical datasets can exceed practical relational-database storage and backup economics by orders of magnitude.

A design that places every source file and every full feature payload in PostgreSQL would couple database growth, vacuum, index maintenance, replication, backup, restore, and query availability to bulk data volume. A design that puts all information only in object storage would lose efficient entity identity, relationship traversal, transactional reconciliation, and indexed spatial lookup.

The architecture therefore needs a deliberate split between bulk bytes and the information index.

## Decision

Adopt a provider-neutral, object-first storage architecture with PostGIS as the operational spatial information index and transaction store.

1. **Object storage is the durable bulk-data plane.** Preserve original source snapshots and large derived datasets as immutable objects. Use S3-compatible APIs initially, without coupling domain contracts to one vendor. Store object URI, object version/generation where available, media/storage format, byte size, required SHA-256 checksum, and non-secret storage metadata.
2. **PostgreSQL/PostGIS is the information and serving index.** Store stable entity IDs, source dataset/snapshot metadata, compact source-record locators, source crosswalks, observations, entity relationships, selected queryable geometries, and spatial indexes. Do not treat it as the universal blob store.
3. **Use columnar geospatial formats for bulk analytical interchange.** Prefer GeoParquet/Parquet for large vector batches and tabular analytical scans; use Cloud Optimized GeoTIFF for suitable raster access; use COPC/LAZ for point clouds; use PMTiles or tiled object layouts for distribution when appropriate. Format choice is workload-specific, not a universal canonical format.
4. **Separate preservation, curation, and serving.**
   - Landing: immutable byte-for-byte source snapshots and manifests.
   - Curated: validated, normalized, partitioned datasets with explicit schema, CRS, lineage, and quality evidence.
   - Serving: selected entity representations, topology, metadata, and indexes needed for interactive and transactional queries.
5. **Process by bounded streaming batches.** Never require a whole national dataset to fit in application memory. Read windows/partitions, validate and transform bounded chunks, write bulk outputs to temporary object keys, and stage compact database rows with PostgreSQL COPY or equivalent bulk insertion. Publish manifests and update snapshot state only after all required objects and database rows are durable. Use deterministic batch IDs/checkpoints so retries are idempotent.
6. **Keep storage references non-secret and durable.** Persist canonical object URIs and immutable version identifiers, never presigned URLs, access keys, or credentials. Resolve credentials at runtime through the deployment's identity/secret mechanism.
7. **Keep PostGIS geometry selective.** Store geometries needed for entity-level spatial search and operational topology. Huge source geometries and analytical intermediates remain in object storage; a source record points to its exact feature locator. For a dataset that needs broad spatial scans, query its partitioned columnar representation with a suitable engine rather than forcing all bytes into the entity table.
8. **Scale by evidence, not premature sharding.** Start with one managed PostgreSQL/PostGIS instance plus object storage and bounded workers. Partition large append-heavy tables only when measured volume/query patterns justify it. Add read replicas, workload-specific analytical engines, regional partitions, or distributed Postgres only when operational evidence requires them. Stable IDs and object references must not depend on any one database shard.

## Migration 0002

Migration `0002_bulk_object_storage_boundary.sql` adds object identity/version/format metadata to source snapshots and allows source records to store either a compact inline JSON payload or a JSON object locator into the immutable snapshot. Existing migration-0001 records remain valid because their inline payloads are preserved.

A locator is descriptive, not a public URL contract. Its shape is adapter/format-specific and must identify the exact feature/row within a checksum-identified snapshot object.

## Consequences

- Raw source data can grow independently of relational database size.
- Source snapshots remain reproducible and can be reprocessed without redownloading providers.
- The database remains useful for entity identity, provenance, reconciliation, relationships, and interactive spatial queries.
- Large imports require object storage, batch orchestration, checksums, manifests, retry-safe checkpoints, and lifecycle/retention policy.
- Object storage is not automatically cheap or simple: request costs, egress, small-object overhead, versioning, replication, and retention must be measured.
- PostgreSQL still needs capacity planning, indexes, vacuum, backups, and restore testing. This decision does not promise infinite scale or eliminate operational costs.

## Alternatives rejected

- **All source bytes in JSONB/PostGIS:** creates unnecessary database bloat and ties backup/restore and index operations to bulk payload size.
- **Object storage only:** weakens transactional identity, crosswalk, history, and indexed entity lookup.
- **Choose a distributed database immediately:** premature before measuring actual access patterns and operational bottlenecks.
- **One format for all geospatial data:** raster, point-cloud, vector, and tile workloads have different access and encoding requirements.

## Required follow-on work

- Object-store adapter with streaming upload/download, checksum verification, multipart upload, immutable-key policy, and lifecycle handling.
- Snapshot manifest contract, state machine, and atomic publication protocol.
- Streaming import runner with bounded memory, COPY-based staging, idempotent batch checkpoints, and resumability.
- Integration tests using a disposable S3-compatible object store and PostgreSQL/PostGIS.
- Dataset-level retention, licensing, access control, backup, restore, and disaster-recovery policy.
- Benchmarks on representative regional and national road-network slices before choosing partition keys or analytical engines.
