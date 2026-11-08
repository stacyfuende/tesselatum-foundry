# ADR-027: Make Run provenance immutable across state transitions

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

A Run is one immutable execution attempt whose lifecycle status changes over time. The local Run repository already rejected transitions after a terminal state, but its generic transition method accepted arbitrary field updates while a Run was queued or running. A caller could therefore change the Cell, Capability, input Artifact snapshots, normalized parameters, Recipe context, worker, or implementation after the attempt had been created.

That would make the final record describe different work from the work originally queued or dispatched.

## Decision

1. Treat Run identity and declared execution provenance as immutable from creation: Run ID, attempt, exact Cell and Capability references, creation time, input snapshots, normalized parameters, retry reference, and Recipe correlation fields.
2. Treat worker identity, implementation identity (including manifest checksum), runtime image digest, and start time as set-once fields. They may be added when the queued Run starts but cannot be replaced later.
3. Continue to allow lifecycle transitions to append events and add terminal outcome evidence such as finish time, outputs, validation report references, resource usage, or error details.
4. Reject any transition that attempts to change an immutable or already-set execution identity field. Validate the resulting record against the canonical Run schema before persisting it.
5. Keep terminal Runs immutable as already established by the Run lifecycle contract.

## Consequences

A Run's final record cannot silently drift away from the declaration, inputs, worker, or implementation that were originally recorded. The local repository enforces this invariant within its current single-process concurrency boundary. A future database-backed repository must preserve the same rule transactionally across processes.

## Alternatives considered

- **Trust callers to update only status and outcome fields:** rejected because the repository is the control-plane boundary and must enforce provenance invariants itself.
- **Make the entire Run record immutable at creation:** rejected because lifecycle status, events, output references, and terminal evidence are necessarily appended during execution.
- **Allow corrections to execution identity on a running Run:** rejected; a changed attempt requires a new Run rather than rewriting history.
