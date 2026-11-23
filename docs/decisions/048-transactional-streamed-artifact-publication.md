# ADR-048: Publish streamed Artifacts only after complete-run verification

- **Status:** Accepted
- **Date:** 2026-11-23
- **Related:** ADR-014, ADR-027, ADR-029, ADR-047

## Context

External sources can be much larger than a worker's memory. Foundry therefore reads them incrementally, groups features into bounded batches, and can execute each batch independently. A source checksum may only be verified when the adapter reaches EOF. Any earlier output is provisional: a later read error, checksum mismatch, worker failure, or whole-output validation failure must invalidate the entire result.

The existing Artifact store publishes immutable content-addressed objects and metadata records. The current batch executor is only a worker bridge; it does not yet provide a transaction spanning source completion, batch processing, whole-output validation, Artifact registration and Run success.

## Decision

A streamed Run MUST use a provisional output transaction with the following phases:

1. **Begin:** create an isolated staging transaction associated with one Run attempt and its immutable input/source evidence. Staging is not an Artifact and is not addressable as a successful output.
2. **Append:** accept only the next expected batch sequence. Verify the processed batch envelope, input/output checksums, offsets and feature counts. Write bytes incrementally to a private staging object; do not retain the complete output in memory.
3. **Seal input:** exhaust every source iterator. Source adapters must complete EOF integrity checks. Record final source evidence and cursor/version state. A source that cannot provide a stable snapshot must be represented as non-snapshot-reproducible.
4. **Seal output:** flush and fsync staged bytes, compute final size and checksum, and produce a bounded summary/index needed by validators. The staged bytes remain unpublished.
5. **Validate:** run independent validation against the complete staged output (or a deterministic streaming validation pass). Validation must cover cross-batch invariants, not merely per-batch shape.
6. **Commit:** only after all sources are complete and validation succeeds, atomically publish the content-addressed object and immutable Artifact metadata. Then transition the Run to succeeded with the output reference and validation evidence.
7. **Abort:** on any failure before commit, mark the transaction aborted, make its staging data unreachable, and ensure no successful Artifact or succeeded Run is visible. Cleanup may be deferred, but aborted staging must never be mistaken for committed output.

## Current implementation status

The local implementation now covers private bounded staging, atomic journal replacement, source-EOF gating, output sealing/checksum, a validation-evidence gate, bounded file-to-object copying, content-addressed object durability before immutable metadata registration, and a stable publication intent that permits same-identity retry after metadata commit. The transaction reaches `committed` only after Artifact metadata is registered.

The recovery entry point can reopen a journal after process restart for reconciliation, but it does not resume batch writes: it verifies matching Artifact metadata, object bytes, and producer Run/attempt identity and repairs the final journal state, or aborts uncommitted work. Publication binds the Artifact metadata to the originating Run ID and attempt. `RunRepository.reconcile_committed_output` verifies those producer fields, Artifact bytes and a passing execution-output report before transitioning the Run to succeeded; repeating the same reconciliation is idempotent.

Not yet implemented: resumable batch checkpoints, cross-process writer leases, independent whole-output critic integration, automatic orphan garbage collection, and a streaming Run orchestrator that invokes both publication and Run reconciliation. The current Artifact publisher is a local filesystem adapter; production object stores must provide equivalent conditional publication and durability semantics.

## Required invariants

- At most one active writer owns a transaction; concurrent append attempts are rejected.
- Batch sequence and feature offsets are contiguous and monotonic; duplicate, missing or reordered batches fail closed.
- Every appended payload is checksum-verified before it is accepted.
- Staging storage is private, quota-controlled and excluded from Artifact lookup, cache lookup and public listing.
- The final Artifact checksum is calculated from the exact committed byte stream, not from a concatenation assembled in memory.
- The object is durable before metadata makes it discoverable. Metadata publication is the commit point; failed metadata publication leaves an unreferenced content-addressed object eligible for garbage collection, never a visible partial Artifact.
- Run success is recorded only after Artifact metadata and validation evidence are durable. If the Run transition fails after object publication, recovery must reconcile the committed Artifact with the still-nonterminal Run; it must not rerun computation blindly.
- Retries create a new Run attempt and a new staging transaction. They may reuse completed deterministic batch outputs only when source identity, source version/query evidence, capability/implementation versions, worker image digest and parameters all match the declared cache policy.
- Credentials and signed access URLs never enter staging manifests, provenance, logs or error messages.
- Resource limits cover total staged bytes, batch count, elapsed time and concurrent transactions. Limits are explicit policy, not hidden free-tier ceilings.

## Recovery model

The implementation must persist a minimal transaction journal with states `open`, `input_sealed`, `output_sealed`, `validated`, `committed` and `aborted`. Journal updates must be atomic and include the Run ID, attempt, transaction ID, expected next batch sequence, staged byte count, rolling checksum state or equivalent resumable digest strategy, and source completion evidence.

A process crash must not turn an open or sealed transaction into a committed Artifact. Recovery either resumes from a verified checkpoint with the same source snapshot/cursor evidence or aborts and requires a new Run attempt. If a source cannot resume at the same logical position, the Run restarts from the beginning.

## Consequences

- Artifact storage gains a streaming write path and a private staging/transaction boundary.
- Whole-output validators must support file/stream inputs or a bounded second pass; they must not require loading a national-scale FeatureCollection into memory.
- Run lifecycle needs explicit reconciliation between Artifact commit and Run success.
- Local filesystem implementation can prove semantics first; production backends must provide equivalent conditional/atomic publication guarantees.
- This decision does not require Foundry to warehouse source data. Only derived outputs explicitly requested by a workflow are candidates for Artifact persistence.

## Alternatives considered

### Publish one Artifact per batch

Rejected as the default. It exposes partial results as independent outputs and pushes transaction semantics onto every consumer. Partitioned output may be introduced later as an explicit Artifact format with a manifest-level commit protocol.

### Buffer the entire output in memory, then call the existing Artifact API

Rejected because memory use scales with total dataset size and defeats bounded processing.

### Mark the Run successful after the final worker batch

Rejected because source EOF integrity, cross-batch validation and durable Artifact publication may still fail.

### Rely on temporary files without a transaction journal

Rejected because crashes leave ambiguous staging state and make safe resume/reconciliation impossible.
