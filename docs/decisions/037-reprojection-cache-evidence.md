# ADR-037: Shared output-critic evidence enables reprojection cache reuse

- **Status:** Accepted
- **Date:** 2026-11-08
- **Supersedes:** The temporary vector.reproject cache-disabled policy in ADR-035.

## Context

Vector.buffer and vector.reproject are deterministic spatial operations with different CRS invariants. Buffer output must remain in its declared measurement/input CRS; reprojection output must equal the Cell's declared target CRS. Both operations otherwise require the same evidence before a deterministic cache hit is safe: non-empty FeatureCollection, preserved feature count and metadata, supported and preserved geometry types, valid finite geometries, and preserved coordinate dimensionality.

The original cache critic identity and required-finding set were buffer-specific, so enabling reprojection caching by reusing that evidence would have been incorrect.

## Decision

1. Version the common output critic as `foundry-spatial-output-critic@0.2.0`. Existing buffer reports produced by the old `foundry-vector-output-critic@0.1.0` are stale for cache reuse and are not accepted.
2. Require the common output findings: FeatureCollection validity, feature count, geometry validity, geometry types, coordinate finiteness, dimensionality, and feature metadata.
3. Require exactly one successful CRS invariant finding: `output.crs_matches_input` for vector.buffer or `output.crs_matches_contract` for vector.reproject. A missing, failed, duplicated, or ambiguous CRS finding invalidates cache evidence.
4. Keep the required assessed dimensions identical across both operations: feature count, feature metadata, CRS, geometry type, geometry validity, coordinate finiteness, and dimensionality.
5. Include the shared critic name/version in the deterministic cache key. The exact capability/version, Cell version and constraints, normalized parameters, immutable input checksum, output contract, implementation manifest checksum, and runtime image digest remain key material.
6. Enable `cache_policy: allowed` for vector.reproject@1.0.0. A hit still requires a successful producer Run, exact output-port provenance, matching output media type/CRS/geometry metadata/rights, current passing critic evidence, and checksum verification of the immutable output Artifact.
7. Preserve the existing buffer cache behavior under the new shared critic version. Old reports and artifacts are not mutated; they simply cannot satisfy the new evidence requirement.

## Consequences

- Both vector capabilities can reuse deterministic outputs without weakening CRS-specific validation.
- Cache evidence is versioned independently of the capability implementation and runtime image.
- A critic upgrade invalidates prior cache candidates until they have been evaluated under the new evidence contract.
- Cache reuse remains evidence-based; a successful Run status alone is insufficient.

## Alternatives considered

- **Treat the reprojection CRS finding as equivalent to the buffer CRS finding without recording the distinction:** rejected because the invariants differ.
- **Disable cache permanently for reprojection:** rejected because the operation is deterministic and its complete output evidence can be validated.
- **Trust any successful validator report:** rejected because old or incomplete evidence may omit dimensions required by the current contract.
