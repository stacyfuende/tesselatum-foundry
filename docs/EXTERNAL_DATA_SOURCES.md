# External spatial data sources

**Status:** External source adapter and Run provenance contracts implemented. Bounded feature-batch transport is implemented as a standalone primitive; direct external worker execution remains pending.

Foundry does not take custody of source datasets by default. A source reference identifies where data lives and records the evidence available to reproduce access. An adapter describes and reads that resource without requiring it to be copied into the Foundry Artifact store.

## Contract

- `ExternalDataReference` identifies provider, dataset, resource URI, optional provider version/ETag/SHA-256, media type, retrieval time and a non-secret selection object.
- Credentials must be injected by runtime configuration. URI user information, query strings and fragments are rejected so signed URLs and tokens do not leak into definitions or provenance.
- `SourceAdapter` exposes `supports`, `describe` and bounded `iter_chunks`.
- Adapters must close resources, honor chunk/byte limits and avoid leaking credentials in errors.
- A checksum is verified at end-of-stream. Callers must not publish derived outputs until iteration completes successfully.
- A provider that exposes no stable version or checksum is still usable, but provenance must not claim snapshot-level reproducibility.

The JSON Schema is `schema/external-data-reference.schema.json`. The initial `LocalFileSourceAdapter` is a minimal reference implementation. It reads local `file://` resources in bounded chunks and does not copy them into Artifact storage.

## Example

```python
from pathlib import Path
from tessellatum_foundry.sources import ExternalDataReference, LocalFileSourceAdapter

path = Path("roads.parquet").resolve()
source = ExternalDataReference(
    provider="customer-filesystem",
    dataset_id="roads-2026-11",
    uri=path.as_uri(),
    media_type="application/vnd.apache.parquet",
)

adapter = LocalFileSourceAdapter()
descriptor = adapter.describe(source)
for chunk in adapter.iter_chunks(source, chunk_size=8 * 1024 * 1024):
    consume_chunk(chunk)
```

This is a byte-stream boundary, not a universal feature model or query engine. Format-specific readers interpret bytes and implement feature/window-level selection. `iter_feature_batches` accepts a feature iterator and emits canonical GeoJSON FeatureCollection payloads bounded by both feature count and encoded byte size. Each batch carries a monotonically increasing sequence, first-feature offset, feature count and SHA-256 checksum. It retains only the current batch in memory, preserves feature order, and rejects a single feature that exceeds the configured byte budget.

Example:

```python
from tessellatum_foundry.sources import iter_feature_batches

for batch in iter_feature_batches(feature_reader.iter_features(source), max_features=2_000, max_bytes=16 * 1024 * 1024):
    process_bounded_batch(batch.payload, batch.checksum_sha256)
```

This is a transport primitive, not yet an end-to-end streaming execution path. It does not implement format readers, provider pagination/window queries, restartable source cursors, worker dispatch, streaming output writers, or Run-level checkpoint/retry semantics. In particular, the current `vector.buffer` Run service still resolves and parses a complete Artifact before invoking its whole-FeatureCollection worker. Run records retain validated source references alongside immutable Artifact snapshots; retries preserve identical source evidence. Direct bounded worker input, authorization and source-aware cache keys remain future integration gates.
