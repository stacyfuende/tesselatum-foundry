# External spatial data sources

**Status:** The initial source-backed `vector.buffer` execution path is implemented and CI-verified for local files: external Geo-Cell binding, source-only queued Run creation, runtime authorization, adapter resolution, incremental GeoJSON/NDJSON reading, bounded feature batches, worker dispatch, independent output validation, EOF-gated transactional Artifact publication and Run reconciliation. Production remote-provider adapters, credential brokering, resumable execution and distributed recovery remain pending.

Foundry does not take custody of source datasets by default. A source reference identifies where data lives and records the evidence available to reproduce access. An adapter describes and reads that resource without requiring it to be copied into the Foundry Artifact store.

## Contract

- `ExternalDataReference` identifies provider, dataset, resource URI, optional provider version/ETag/SHA-256, media type, retrieval time and a non-secret selection object.
- Credentials must be injected by runtime configuration. URI user information, query strings and fragments are rejected so signed URLs and tokens do not leak into definitions or provenance.
- `SourceAdapter` exposes `supports`, `describe` and bounded `iter_chunks`.
- Adapters must close resources, honor chunk/byte limits and avoid leaking credentials in errors.
- A checksum is verified at end-of-stream. Callers must not publish derived outputs until iteration completes successfully.
- A provider that exposes no stable version or checksum is still usable, but provenance must not claim snapshot-level reproducibility.

The JSON Schema is `schema/external-data-reference.schema.json`. Geo-Cell input bindings can now declare `source: external`, a provenance-bearing reference, and explicit vector spatial metadata (CRS and geometry types). `ExternalVectorBufferRunFactory` validates the exact Capability, media type, geometry types, projected measurement CRS and source identity, then creates a queued Run with no fake Artifact snapshot and an immutable source reference. Retries must preserve that exact reference. The factory itself does not fetch data or authorize access; `ExternalVectorBufferRunOrchestrator` joins the factory-created Run to runtime authorization, adapter resolution, worker execution and finalization. The initial `LocalFileSourceAdapter` is a minimal reference implementation. It reads local `file://` resources in bounded chunks and does not copy them into Artifact storage.

## Bounded feature batches

This is a byte-stream boundary, not a universal feature model or query engine. Format-specific readers interpret bytes and implement feature/window-level selection. `iter_feature_batches` accepts a feature iterator and emits canonical GeoJSON FeatureCollection payloads bounded by both feature count and encoded byte size. Each batch carries a monotonically increasing sequence, first-feature offset, feature count and SHA-256 checksum. It retains only the current batch in memory, preserves feature order, and rejects a single feature that exceeds the configured byte budget.

`NdjsonFeatureReader` is the first concrete incremental format reader. It decodes one GeoJSON Feature per line, handles chunk boundaries and CRLF, caps individual record size, preserves order, and rejects non-empty selections because it does not implement filtering or query pushdown. `iter_external_feature_batches` composes the source adapter, reader and batcher into a single lazy pipeline.

## Allowlisted HTTPS adapter

`HttpSourceAdapter` is the first remote-source transport implementation. It is deliberately a constrained HTTPS adapter, not an unrestricted URL fetcher:

- HTTPS only, default port only, and exact-match host allowlist (no wildcard suffixes).
- Runtime credential/header resolver is injected per adapter instance; secrets are never written to the source reference or provenance record.
- Redirects are rejected so runtime credentials cannot be forwarded to an unreviewed destination. Register the final host explicitly.
- HEAD metadata and GET streaming use bounded timeouts and bounded read chunks; optional maximum source bytes, ETag and SHA-256 checks are enforced.
- Credential resolver, transport and response errors are exposed as generic redacted source-access errors.
- Header injection and transport-controlled headers are rejected.

The adapter is appropriate for explicitly allowlisted object/API hosts where a stable HTTPS resource URL is available. It does not implement OAuth refresh, provider pagination, cloud object signing, IP-range/DNS rebinding defenses, range-resume, or provider-specific query pushdown. Those belong in separately reviewed provider adapters and the runtime credential broker. The caller remains responsible for configuring a narrow host allowlist and source authorization policy.

## Batch worker bridge

`VectorBufferBatchExecutor` adapts the existing `vector.buffer` worker protocol to one bounded `FeatureBatch` at a time. Before dispatch it verifies the input payload checksum, sequence/offset/count metadata and FeatureCollection shape. It pins the runtime image identity, rejects worker outputs with a different feature count, canonicalizes the output payload and records its checksum, worker-reported CRS, original batch offset and sequence.

This adapter is deliberately not a Run executor. It does not publish Artifacts, checkpoint progress, or transition a Run. It is a tested worker boundary that can be composed into a streaming lifecycle without changing the existing whole-Artifact worker contract.

## Bounded independent output validation

`VectorBufferStreamingValidator` validates each paired input/output batch with the existing independent `vector.buffer` critic, using the worker-reported output CRS rather than assuming the declared CRS was honored. It aggregates findings, geometry types, feature counts and worker duration while retaining no complete FeatureCollection. It rejects missing/reordered batches, offset/count mismatches, altered input/output checksums, and worker-image changes. An empty stream cannot pass. This supplies a bounded validation primitive. `StreamingVectorBufferPipeline` now composes it with the batch executor, provisional transaction and Run finalizer.

## Integrity and publication boundary

A source checksum is verified only when the byte stream reaches EOF. Consumers MUST stage provisional batch results and MUST NOT publish output Artifacts or mark a Run successful until the source iterator is exhausted without error. A later batch failure or EOF checksum mismatch invalidates the entire provisional result set.

The existing Artifact-backed `vector.buffer` Run service remains unchanged and continues to use its whole-FeatureCollection worker. For external bindings, `ExternalVectorBufferRunFactory` creates a source-backed queued Run and `ExternalVectorBufferRunOrchestrator` joins it to runtime authorization, adapter resolution, Run start, bounded source iteration, worker dispatch, validation, transaction construction, Artifact publication and Run reconciliation. The orchestrator currently supports the initial `vector.buffer` capability and configured adapters/readers; it does not yet provide provider pagination, resumable checkpoints or a production credential broker.

## Remaining integration gates

- Resumable checkpoints, process-restart writer reopening and cross-process writer ownership; current recovery is conservative and aborts uncommitted work rather than resuming it.
- Integrate source rights declarations and methodology evidence into streaming Run preconditions and output validation. Runtime authorization is currently an injected callback; it does not itself infer legal permission or source suitability.
- Run-level checkpoint/retry semantics with stable source cursor/version evidence.
- Provider pagination, spatial/temporal windows and query pushdown.
- Production runtime authorization and scoped credential brokering/rotation; the orchestrator currently accepts injected authorization and adapter-resolution callables.
- Source-aware cache identity and explicit semantics when provider version evidence is absent.
- Additional format readers chosen against real workloads, not an untested format matrix.

The source path does not warehouse upstream data. Optional derived outputs remain subject to explicit ownership, access and retention policy. The current external binding supports only media types already accepted by the exact Capability contract; NDJSON remains a separate reader format and is not silently treated as the vector.buffer 1.0.0 FeatureCollection media type.


## Provisional output staging

The local storage adapter now includes `StreamingFeatureCollectionTransaction`. It appends verified processed batches to a private provisional GeoJSON FeatureCollection, enforcing contiguous sequence/offsets, batch count and output byte limits. It persists an atomic journal after each accepted batch, requires explicit source EOF verification before sealing, computes a checksum over the sealed output, and requires passing validation evidence before reaching the `validated` state.

A validated transaction can now call `publish_artifact` to stream the staged file into the local content-addressed Artifact store. The store hashes and copies in bounded chunks, fsyncs the object before registering immutable metadata, and leaves an unreferenced object (eligible for later garbage collection) if metadata publication fails. The transaction journals a stable Artifact identity before publication; retrying that identity is idempotent if metadata was committed but the final transaction-journal update was interrupted. `committed` is recorded only after Artifact metadata is available.

The transaction recovery entry point can reconcile a journal after process restart: if the journal contains a publication intent and matching durable Artifact metadata/object can be verified, including producer Run and attempt identity, it repairs the journal to `committed`; otherwise it aborts the incomplete attempt. It deliberately does not resume batches. Publication automatically binds Artifact metadata to the originating Run ID and attempt. `RunRepository.reconcile_committed_output` separately verifies those producer fields, the Artifact bytes and a passing execution-output report before transitioning a running Run to succeeded, and is idempotent for the same output/report pair.

`StreamingVectorBufferPipeline` connects source-batch iteration, worker dispatch, bounded independent validation, EOF-gated transaction sealing, persisted validation evidence, Artifact publication and Run reconciliation. `ExternalVectorBufferRunFactory` creates source-only queued Runs from explicit Geo-Cell external bindings, without inventing Artifact snapshots. `ExternalVectorBufferRunOrchestrator` joins these components for the initial local-source `vector.buffer` path. Cross-process writer leases, resumable checkpoints and automatic recovery scheduling remain pending. Rights/methodology policy and production-grade runtime credential brokering must be integrated before treating this as a complete production Run service. A committed Artifact does not by itself mark its Run successful; the Run reconciliation step must be invoked.


## STAC Item asset resolution

The STAC integration currently resolves a single, already-discovered STAC Item
asset; it is not yet a catalog crawler or STAC API client. `parse_stac_item`
accepts bounded UTF-8 JSON (2 MiB by default). `resolve_stac_asset` requires
a STAC Item identity, collection, selected asset, caller-supplied catalog ID
and exact HTTPS asset-host allowlist. It produces an `ExternalDataReference`
whose dataset/resource identity is derived from catalog, collection, Item and
asset key. Version evidence is selected from the Item's version, updated,
datetime or created properties. A supported `file:checksum` SHA-256 multihash
is converted to the source reference checksum.

Asset hrefs containing credentials, query parameters, fragments, non-default
ports, non-HTTPS schemes or unapproved hosts are rejected. In particular,
expiring signed URLs are not persisted: the HTTP adapter's runtime credential
resolver must provide access separately. Catalog discovery, pagination,
conformance negotiation, alternate asset selection and provider-specific
authentication remain separate future integrations.


## Bounded STAC Item retrieval

`StacItemSourceResolver` now joins catalog metadata retrieval to asset resolution.
It accepts a known Item endpoint as an `ExternalDataReference`, reads it through
an injected source adapter with an explicit metadata byte budget, parses the
Item, and resolves the requested asset against a separate exact asset-host
allowlist. It does not crawl collections, perform search pagination, or fetch
the selected asset. The resulting asset reference can be passed to the existing
HTTPS adapter and external feature pipeline when its media type is supported.
Catalog and asset hosts are intentionally governed independently.


## Live STAC provider smoke test

An opt-in integration test at `tests/integration/test_live_stac.py` exercises
the real catalog transport and Item resolver against a public provider. It is
disabled unless all of these environment variables are supplied:

- `FOUNDRY_STAC_ITEM_URL`: one known Item endpoint, without query parameters.
- `FOUNDRY_STAC_CATALOG_HOST`: the exact catalog hostname.
- `FOUNDRY_STAC_ASSET_HOSTS`: comma-separated exact asset hostnames.
- `FOUNDRY_STAC_ASSET_KEY`: the asset key to resolve.

Run it with `python -m pytest -m integration tests/integration/test_live_stac.py`.
The smoke test resolves metadata and checks the resulting asset locator; it
does not download or process the asset. Provider availability is best-effort,
so this test is intentionally not part of deterministic pull-request CI.

**Format boundary:** STAC is a discovery/metadata standard, not a raster
processing implementation. Earth-observation catalogs commonly advertise
Cloud Optimized GeoTIFF (COG) assets. The current source-backed execution path
is vector-only and accepts only the formats declared by its vector Capability
and incremental readers (GeoJSON FeatureCollection and NDJSON). A resolved
COG reference is useful provenance, but cannot yet be sent to
`vector.buffer`. Raster range reads, raster window readers, grid/tile
semantics and raster Capabilities must be implemented as a separate path;
do not disguise raster bytes as vector features.


## Bounded STAC API search

`StacApiSearchClient` adds a bounded search boundary for an already-known
STAC API `/search` endpoint. It submits a POST query with optional bbox or
GeoJSON intersects, datetime interval, collection IDs, Item IDs and page
limit, then yields Items one page at a time. It does not accumulate a complete
catalog result set.

Pagination follows only a single explicit `rel=next` link per page. Both the
initial endpoint and every next-link URL must use HTTPS, default port and an
exact allowlisted hostname. GET and POST next links are supported; redirects
must be disabled by the injected transport. Page bytes, page count and total
Item count are independently bounded. Cycles, malformed pages, unapproved
hosts, duplicate next links and invalid query constraints fail closed.

The transport is intentionally injected rather than silently reusing the
generic file adapter: STAC search requires POST bodies and some providers
return transient cursor query parameters in next links. These URLs are
ephemeral request state only; callers must not persist them as
`ExternalDataReference` values or log them. The transport is responsible for
TLS validation, timeouts, runtime credential injection, bounded reads and
refusing redirects. This client does not implement provider-specific auth,
catalog conformance negotiation, asynchronous search jobs or spatial query
planning. Search results are Items; resolve selected assets through
`StacItemSourceResolver` and the separate asset-host policy.


## STAC HTTPS search transport

`UrllibStacSearchTransport` is the reference transport for the bounded STAC
search client. It uses Python's default TLS certificate validation, an exact
host allowlist checked on every request, a finite timeout, and a bounded
response read. Redirects are rejected rather than followed. A runtime header
resolver may inject scoped credentials for a request; header values are
validated against CR/LF injection and transport-controlled headers cannot be
overridden. HTTP failures are exposed as generic redacted transport errors.
The transport is intentionally separate from `HttpSourceAdapter`: STAC
search needs POST JSON bodies and ephemeral cursor URLs, while source adapters
identify stable resources for data reads.

An opt-in public-catalog integration test at
`tests/integration/test_live_stac_search.py` uses Earth Search's v1 search
endpoint to discover an Item and resolve one allowlisted asset reference. It
is disabled in normal pull-request CI. Configure
`FOUNDRY_STAC_ASSET_HOSTS` with exact asset hostnames and optionally
`FOUNDRY_STAC_SEARCH_URL` to select a compatible public STAC API endpoint.
The test only resolves metadata; it does not download the raster asset.


## Exact HTTP byte-range reads

`HttpSourceAdapter.read_range` now provides the transport primitive required
for remote formats whose metadata and data blocks can be accessed by byte
offset, including Cloud Optimized GeoTIFF. It issues a single bounded HTTP
Range request and accepts only HTTP 206 with an exact `Content-Range`, exact
payload length and identity content encoding. When the source reference has an
ETag, the request includes `If-Match` and the response ETag is checked again.
The caller sets a maximum range size (16 MiB by default); a server that ignores
Range and returns the full object is rejected rather than silently downloaded.

This is deliberately only a byte-addressed transport primitive. It does not
parse TIFF/GeoTIFF headers, validate COG layout, interpret overviews or
georeferencing, select raster windows, decode pixels, or prove that a provider
honors stable snapshot semantics. Those responsibilities belong in a
raster-specific reader and validation contract. A raster reader must use
bounded range requests for header, IFD, tile/strip and overview access, enforce
a cumulative request/byte budget, and verify that all ranges belong to one
stable object version (ETag or equivalent) before publishing derived results.
The vector FeatureCollection pipeline remains unchanged.


## Raster grid and range-read contracts

The first raster-specific contracts are represented independently of any
pixel library. RasterMetadata records grid dimensions, per-band dtypes,
six-coefficient affine transform, optional CRS and NoData values, block shapes
and overview factors. RasterWindow uses zero-based pixel offsets and
dimensions with optional one-based band indexes; windows are checked against
the declared grid before execution.

BudgetedRasterRangeReader wraps a byte-range adapter with cumulative request,
total-byte and per-request byte limits. It requires a strong ETag because the
current HTTP adapter uses If-Match to pin each range to one source
representation. Failed attempts consume budget. This is a safe transport
boundary, not a TIFF/COG decoder: no IFD parsing, COG conformance validation,
overview selection or pixel decoding is claimed yet. A future reader must
derive and validate RasterMetadata from bounded source reads before exposing
windows to a raster worker.


## Bounded TIFF metadata inspection

`TiffRangeReader` now reads the TIFF header and first image file directory
through `BudgetedRasterRangeReader`. It recognizes classic TIFF and BigTIFF
byte order/header layouts, bounds IFD entry counts and individual tag payloads,
and extracts image dimensions, sample representation, compression, strip or
tile byte ranges, and affine georeferencing from GeoTIFF transformation or
pixel-scale/tiepoint tags. It rejects out-of-file metadata/data ranges,
duplicate tags, unsupported sample representations and incomplete strip/tile
tables. It requires the strong ETag and cumulative range budgets enforced by
the wrapped reader.

This is an initial metadata reader, not a COG validator or raster decoder. It
currently reads only the first IFD, does not traverse SubIFDs or overview
directories, does not interpret GeoKeyDirectoryTag into a normalized CRS,
does not prove COG ordering/alignment/layout, and does not decompress tiles or
strips. The returned grid therefore has no CRS unless supplied by a later
georeferencing resolver. Do not expose arbitrary pixel windows as executable
until those remaining checks and a bounded block decoder are implemented.


### TIFF directory graph traversal

The TIFF reader also exposes a bounded directory index. It follows the primary
next-IFD chain and recursively referenced SubIFDs using a queue, rejects cycles
and duplicate directory references, limits total directory count and per-IFD
entry count, and records each directory's dimensions and strip/tile byte
ranges. This is enough to inventory the image-directory graph and identify
candidate reduced-resolution images without reading their pixel blocks.

For tiled directories, the index also records tile width/height, samples per
pixel, planar configuration, compression and NewSubfileType. It checks that
tile dimensions are positive and that the tile-offset table length matches the
image grid (including separate-planar sample planes). The index follows both
primary next-IFD links and SubIFD links; it does not assume every later IFD is
an overview.

A conservative `assess_cog_structure` helper reports whether inspected directories pass a limited set of COG-like checks: tiled primary image, smaller directories marked reduced-resolution, matching tile dimensions, and compatible sample/planar layouts. This is **not** a COG conformance verdict. It does not establish normative IFD/tile ordering or byte-range alignment, parse GeoKeys into normalized CRS, validate compression semantics, or decode pixel blocks. Production COG capability still requires those checks and a bounded decoder.


## Raster window tile planning

The raster source layer now includes `select_tiff_tiles`, which maps a validated
zero-based `RasterWindow` to the TIFF tile byte ranges that intersect it. The
planner accounts for tile-grid edges and both chunky and planar-separated
sample layouts. Its output includes the complete encoded tile range and the
pixel intersection within the tile, allowing a later decoder to crop the
requested window without reading unrelated tiles.

The planner enforces a maximum selected-tile count and validates the directory
tile-table shape against the raster dimensions and sample layout. The resulting
ranges can be fetched through `BudgetedRasterRangeReader`, which applies the
shared request/byte budget and requires a strong ETag on the source reference.

This is range selection, not pixel decoding. Compression handling, decompression
bomb limits, decoded-memory budgets, resampling, and a complete COG conformance
validator remain separate work.


## Sequential raster tile range retrieval

`read_selected_tiff_tiles` consumes the selections produced by
`select_tiff_tiles` and fetches one encoded tile range at a time through
`BudgetedRasterRangeReader`. Each yielded tile includes its selection,
encoded bytes and SHA-256 digest. The iterator does not retain previously
yielded payloads; callers should process and release each tile before
advancing. All reads share the same cumulative request and byte budgets and
the same strong-ETag source validator.

The returned bytes are still compressed/encoded TIFF tile data. This component
does not decompress, interpret sample values, assemble a multi-tile window or
enforce decoded-array memory limits. Those must be provided by a subsequent
format-aware decoder before the raster path can be treated as executable.

## Bounded uncompressed TIFF tile sample decoding

`decode_uncompressed_tiff_tile` is the first deliberately narrow pixel-decoding
boundary. It accepts one retrieved tile, verifies that its selection matches
the directory's tile table, checks the sample layout and decoded-size budgets,
and exposes the sample buffer with its TIFF byte order and per-sample dtypes.
Chunky data remains pixel-interleaved; planar-separated data must identify one
one-based band. TIFF edge tiles are validated using their full encoded tile
dimensions, including padding outside the image grid.

This initial decoder accepts only Compression=1 (uncompressed), Predictor=1,
and supported byte-aligned integer/float sample dtypes. It rejects packed
samples, compression codecs, predictors, malformed payload lengths and tiles
over the configured decoded-byte or pixel limits. It does not yet decompress
Deflate/LZW/JPEG, undo predictors, normalize byte order, convert photometric
interpretations, rescale samples, or assemble a multi-tile raster window.
The returned sample bytes retain the source TIFF byte order; consumers must
interpret them using the returned dtype and byte-order metadata. Its lazy
`iter_pixels()` interface unpacks one pixel tuple at a time (interleaved bands
for chunky tiles, one selected band for planar tiles), without materializing a
full decoded array. This is a bounded raw-sample extraction primitive, not yet
a general-purpose raster decoder.

### Bounded TIFF Deflate decoding

`decode_deflate_tiff_tile` adds support for TIFF Compression=8 and the
legacy Deflate code 32946 using the zlib-wrapped Deflate stream. The compressed
input has its own byte limit; the expected output size is derived from the
declared tile dimensions and supported sample dtypes. Decompression is capped
at expected-size-plus-one bytes and rejects truncated streams, trailing data,
and output whose length differs from the exact tile sample layout.

Horizontal differencing (Predictor=2) is reversed for supported integer sample types using a bounded tile buffer; floating-point Predictor=2 is rejected. Predictor=1 remains supported.
Raw decoded samples retain source byte order and use the same lazy pixel
iterator as uncompressed tiles. The unified `decode_tiff_tile` entry point dispatches only to the explicitly supported compression and predictor combinations. Raw Deflate streams, LZW, JPEG, packed samples,
photometric conversion, and multi-tile window assembly are not supported.

