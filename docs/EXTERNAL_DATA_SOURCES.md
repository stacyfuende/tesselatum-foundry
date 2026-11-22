# External spatial data sources

**Status:** Initial adapter contract implemented; Run integration pending.

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

This is a byte-stream boundary, not a universal feature model or query engine. Format-specific readers will interpret bytes and implement feature/window-level selection. The current adapter is not yet wired into Run input resolution, worker staging, authorization or cache keys. Those are the next integration gates.
