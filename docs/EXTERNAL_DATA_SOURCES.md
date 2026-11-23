# External spatial data sources

**Status:** External source adapter, Run provenance, incremental NDJSON reader, bounded feature-batch pipeline, batch-aware worker bridge, per-batch independent output critic, provisional output staging, local streamed Artifact publication, Run finalization/reconciliation and a bounded streaming execution pipeline are implemented. Direct external-source Run creation/resolution, production source adapters and distributed recovery remain pending.

Foundry does not take custody of source datasets by default. A source reference identifies where data lives and records the evidence available to reproduce access. An adapter describes and reads that resource without requiring it to be copied into the Foundry Artifact store.

## Contract

- `ExternalDataReference` identifies provider, dataset, resource URI, optional provider version/ETag/SHA-256, media type, retrieval time and a non-secret selection object.
- Credentials must be injected by runtime configuration. URI user information, query strings and fragments are rejected so signed URLs and tokens do not leak into definitions or provenance.
- `SourceAdapter` exposes `supports`, `describe` and bounded `iter_chunks`.
- Adapters must close resources, honor chunk/byte limits and avoid leaking credentials in errors.
- A checksum is verified at end-of-stream. Callers must not publish derived outputs until iteration completes successfully.
- A provider that exposes no stable version or checksum is still usable, but provenance must not claim snapshot-level reproducibility.

The JSON Schema is `schema/external-data-reference.schema.json`. The initial `LocalFileSourceAdapter` is a minimal reference implementation. It reads local `file://` resources in bounded chunks and does not copy them into Artifact storage.

## Bounded feature batches

This is a byte-stream boundary, not a universal feature model or query engine. Format-specific readers interpret bytes and implement feature/window-level selection. `iter_feature_batches` accepts a feature iterator and emits canonical GeoJSON FeatureCollection payloads bounded by both feature count and encoded byte size. Each batch carries a monotonically increasing sequence, first-feature offset, feature count and SHA-256 checksum. It retains only the current batch in memory, preserves feature order, and rejects a single feature that exceeds the configured byte budget.

`NdjsonFeatureReader` is the first concrete incremental format reader. It decodes one GeoJSON Feature per line, handles chunk boundaries and CRLF, caps individual record size, preserves order, and rejects non-empty selections because it does not implement filtering or query pushdown. `iter_external_feature_batches` composes the source adapter, reader and batcher into a single lazy pipeline.

## Batch worker bridge

`VectorBufferBatchExecutor` adapts the existing `vector.buffer` worker protocol to one bounded `FeatureBatch` at a time. Before dispatch it verifies the input payload checksum, sequence/offset/count metadata and FeatureCollection shape. It pins the runtime image identity, rejects worker outputs with a different feature count, canonicalizes the output payload and records its checksum, worker-reported CRS, original batch offset and sequence.

This adapter is deliberately not a Run executor. It does not publish Artifacts, checkpoint progress, or transition a Run. It is a tested worker boundary that can be composed into a streaming lifecycle without changing the existing whole-Artifact worker contract.

## Bounded independent output validation

`VectorBufferStreamingValidator` validates each paired input/output batch with the existing independent `vector.buffer` critic, using the worker-reported output CRS rather than assuming the declared CRS was honored. It aggregates findings, geometry types, feature counts and worker duration while retaining no complete FeatureCollection. It rejects missing/reordered batches, offset/count mismatches, altered input/output checksums, and worker-image changes. An empty stream cannot pass. This supplies a bounded validation primitive. `StreamingVectorBufferPipeline` now composes it with the batch executor, provisional transaction and Run finalizer.

## Integrity and publication boundary

A source checksum is verified only when the byte stream reaches EOF. Consumers MUST stage provisional batch results and MUST NOT publish output Artifacts or mark a Run successful until the source iterator is exhausted without error. A later batch failure or EOF checksum mismatch invalidates the entire provisional result set.

The existing Artifact-backed `vector.buffer` Run service remains unchanged and continues to use its whole-FeatureCollection worker. The new `StreamingVectorBufferPipeline` is a separate execution path for an already-created and running Run: it exhausts the supplied source-batch iterator, dispatches and validates each batch, seals the source only after normal iterator completion, persists the aggregate report, and invokes transactional Artifact publication and Run reconciliation. It does not yet create the Run or resolve an external source reference from a Geo-Cell declaration.

## Remaining integration gates

- Direct external source inputs in Run orchestration and worker dispatch.
- Wire the bounded aggregate critic into streamed Run orchestration and persist its report before the staging validation gate.
- Resumable checkpoints, process-restart writer reopening and cross-process writer ownership; current recovery is conservative and aborts uncommitted work rather than resuming it.
- Integrate rights and methodology evidence into streaming Run preconditions and output validation; the pipeline currently accepts caller-supplied rights metadata but does not infer authorization or methodology suitability.
- Run-level checkpoint/retry semantics with stable source cursor/version evidence.
- Provider pagination, spatial/temporal windows and query pushdown.
- Runtime authorization and scoped credential injection.
- Source-aware cache identity and explicit semantics when provider version evidence is absent.
- Additional format readers chosen against real workloads, not an untested format matrix.

The source path does not warehouse upstream data. Optional derived outputs remain subject to explicit ownership, access and retention policy.


## Provisional output staging

The local storage adapter now includes `StreamingFeatureCollectionTransaction`. It appends verified processed batches to a private provisional GeoJSON FeatureCollection, enforcing contiguous sequence/offsets, batch count and output byte limits. It persists an atomic journal after each accepted batch, requires explicit source EOF verification before sealing, computes a checksum over the sealed output, and requires passing validation evidence before reaching the `validated` state.

A validated transaction can now call `publish_artifact` to stream the staged file into the local content-addressed Artifact store. The store hashes and copies in bounded chunks, fsyncs the object before registering immutable metadata, and leaves an unreferenced object (eligible for later garbage collection) if metadata publication fails. The transaction journals a stable Artifact identity before publication; retrying that identity is idempotent if metadata was committed but the final transaction-journal update was interrupted. `committed` is recorded only after Artifact metadata is available.

The transaction recovery entry point can reconcile a journal after process restart: if the journal contains a publication intent and matching durable Artifact metadata/object can be verified, including producer Run and attempt identity, it repairs the journal to `committed`; otherwise it aborts the incomplete attempt. It deliberately does not resume batches. Publication automatically binds Artifact metadata to the originating Run ID and attempt. `RunRepository.reconcile_committed_output` separately verifies those producer fields, the Artifact bytes and a passing execution-output report before transitioning a running Run to succeeded, and is idempotent for the same output/report pair.

`StreamingVectorBufferPipeline` now connects source-batch iteration, worker dispatch, bounded independent validation, EOF-gated transaction sealing, persisted validation evidence, Artifact publication and Run reconciliation for an already-running Run. The existing Artifact-backed Run service is unchanged. Direct external-source Run creation/resolution, Geo-Cell external bindings, cross-process writer leases, resumable checkpoints and automatic recovery scheduling remain pending. Rights/methodology policy must be integrated before treating this as a complete production Run service. A committed Artifact does not by itself mark its Run successful; the Run reconciliation step must be invoked.
