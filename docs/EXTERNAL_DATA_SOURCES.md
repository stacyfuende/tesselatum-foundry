# External spatial data sources

**Status:** External source adapter, Run provenance, incremental NDJSON reader and bounded feature-batch pipeline implemented. Direct external worker execution remains pending.

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

`NdjsonFeatureReader` is the first concrete incremental format reader. It decodes one GeoJSON Feature per line, handles chunk boundaries and CRLF, caps individual record size, preserves order, and rejects non-empty selections because it does not implement filtering or query pushdown. `iter_external_feature_batches` composes the source adapter, reader and batcher into a single lazy pipeline.

Example:

```python
from tessellatum_foundry.sources import (
    ExternalDataReference,
    LocalFileSourceAdapter,
    NdjsonFeatureReader,
    iter_external_feature_batches,
)

source = ExternalDataReference(
    provider="customer-filesystem",
    dataset_id="roads.ndjson",
    uri=roads_path.as_uri(),
    media_type="application/x-ndjson",
)
for batch in iter_external_feature_batches(
    source,
    adapter=LocalFileSourceAdapter(),
    reader=NdjsonFeatureReader(),
    max_batch_features=2_000,
    max_batch_bytes=16 * 1024 * 1024,
):
    stage_batch_for_worker(batch.payload, batch.checksum_sha256)
```

This is a bounded source-to-batch data path, not yet a complete Run execution path. Adapters and readers are lazy; the pipeline does not warehouse the source. A source checksum is verified only when the byte stream reaches EOF, so consumers MUST stage provisional batch results and MUST NOT publish output Artifacts or mark a Run successful until the iterator is exhausted without error. The current `vector.buffer` Run service still resolves and parses a complete Artifact before invoking its whole-FeatureCollection worker. Provider pagination/window pushdown, restartable source cursors, batch-aware worker dispatch, streaming output writers, Run-level checkpoint/retry semantics, runtime authorization and source-aware cache keys remain future integration gates.
