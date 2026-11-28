# Foundry architecture: spatial computation infrastructure

**Status:** Accepted direction for ongoing implementation  
**Date:** 2026-11-22  
**Supersedes:** The storage-centric direction proposed in ADR-045 and ADR-046.

## 1. Decision

Tessellatum Foundry is the engineering foundation for **unified infrastructure for spatial data**. Its job is to make spatial data computable, composable, validated, reproducible and accessible to applications.

Foundry is not intended to become the permanent owner, warehouse or global catalogue of all spatial datasets. Data ownership remains with its source provider, customer, or chosen storage platform. Foundry connects to those sources through explicit interfaces and processes only the data required for a declared computation.

## 2. What Foundry owns

Foundry owns the computational system and its contracts:

- versioned, engine-independent Capability contracts;
- conformance-tested, replaceable Implementations;
- declarative and versioned Geo-Cells;
- composable, validated Recipe graphs;
- Run lifecycle, events, retry identity and execution provenance;
- isolated worker dispatch and resource enforcement;
- independent input/output validation and methodological evidence;
- immutable definitions and computational artifacts;
- SDK/API contracts for applications and services.

Foundry may persist definitions, Run records, validation reports, caches and derived outputs. Such persistence is scoped to the computational product and has explicit lifecycle/retention semantics. It does not imply bulk ownership of source datasets.

## 3. External data boundary

External spatial data may be accessed through:

- local paths and mounted volumes;
- customer-controlled object storage;
- provider APIs and query services;
- customer databases and spatial databases;
- remote file and tile services;
- explicitly supplied immutable artifacts.

The connector boundary should expose metadata and bounded access, not force every source into a Foundry database. Prefer windowed reads, streaming, pagination, spatial/temporal filters and provider-side pushdown. A computation must declare what subset it needs and fail clearly when the source cannot satisfy the request.

A source reference should capture as available:
- provider and dataset identity;
- resource locator (without embedding credentials or expiring signed secrets);
- provider version, object version, ETag or checksum;
- retrieval/query parameters and filters;
- observed time and relevant temporal coverage;
- format, CRS and schema metadata;
- licensing/attribution declarations and known access constraints.

A locator alone is not a reproducibility guarantee. If a source is mutable and supplies no immutable version or checksum, the Run must record that limitation. A customer may choose to supply or retain an immutable snapshot, but Foundry must not silently copy the entire source to achieve this.

## 4. Computation lifecycle

The canonical flow is:

1. **Describe** — declare the source reference and the exact data requirement.
2. **Resolve** — verify access, metadata, schema, CRS, temporal/spatial coverage and version evidence.
3. **Read** — stream or window the required data into a bounded worker working set.
4. **Execute** — run the selected conformant implementation using a resolved Geo-Cell/Recipe.
5. **Inspect** — independently validate output and record limitations.
6. **Register** — persist derived artifacts and Run evidence according to retention policy.
7. **Reuse** — reuse cache entries only when source identity/version evidence and all other cache-relevant inputs match.

The control plane must not assume every worker can reach every source. Access must be explicit, scoped, auditable and passed through a secure credential mechanism; credentials must never be written into definitions, Run manifests or logs.

## 5. Persistence policy

| Data class | Default treatment |
|---|---|
| Source datasets | Remain external; do not bulk-ingest by default |
| Source metadata and references | Record only the minimum needed for resolution and provenance |
| Temporary working data | Worker-local or customer-controlled scratch; bounded and cleaned by policy |
| Cell and Recipe definitions | Persist immutably |
| Run events and provenance | Persist as execution records |
| Validation reports | Persist with exact subject identity |
| Derived outputs | Register as immutable Artifacts when the workflow requires them |
| Cache entries | Optional, bounded, validation-gated and evictable |
| Large output files | May use a customer-selected object store or artifact backend; not a Foundry-owned source-data lake |

The existing filesystem Artifact store is a local adapter, not a claim that all data belongs on one machine. Storage backends can evolve independently of computation contracts.

## 6. Architecture planes

- **Control plane:** contracts, definitions, graph validation, source references, authorization, scheduling, Run lifecycle, provenance and cache policy.
- **Compute plane:** isolated workers, capability implementations, bounded reads, temporary scratch, output staging and resource accounting.
- **Data plane:** the provider/customer systems that already own the spatial data. Foundry adapters connect to them without requiring central ingestion.
- **Artifact plane:** optional persistence for immutable computational outputs and definitions, with explicit ownership and retention.

These planes are logical boundaries, not a requirement to deploy four separate services.

## 7. Engineering sequence

1. Keep the proven Capability/Geo-Cell/Recipe/Run/Artifact contracts intact.
2. Finish execution hardening: concurrency limits, process isolation, timeouts, resource accounting and cancellation.
3. Integrate raster operations into the Run and Recipe lifecycle.
4. Define a minimal external-data source protocol and local adapter, then test bounded reads and failure behavior.
5. Add source-reference provenance to Run specifications and cache keys.
6. Build authenticated project/Cell/Recipe/Run/Artifact APIs and generated client SDK.
7. Build a usable workspace and Recipe Studio.
8. Expand adapters and capabilities only against real use cases.

## 8. Explicit non-goals

- A universal global spatial database.
- A mandatory copy of customer or provider datasets.
- A general-purpose source-data ingestion and reconciliation platform.
- A permanent archive of every input.
- A forced universal spatial file format.
- A distributed database or compute cluster before workload evidence.
- Arbitrary user code in the trusted worker path.
- An AI system that can bypass contracts, authorization or validation.

## 9. Relationship to Spatial Methods and products

Spatial Methods remains the knowledge and methods foundation. Foundry turns methods into executable, testable, reusable computational capabilities. Tessellatum products consume these capabilities where useful; they retain responsibility for their own domain-specific data ownership and customer commitments.

## 10. Definition of success

A user can connect spatial data where it already lives, declare a computation, validate its requirements, execute it on a compatible worker without loading the whole dataset unnecessarily, inspect the result, and trace the Run to the source evidence, exact capability and implementation versions, parameters, runtime and validation report.

Foundry succeeds by making spatial computation dependable—not by accumulating the world's spatial data.
