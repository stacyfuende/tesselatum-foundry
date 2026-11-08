# ADR-014: Retries create new Run attempts

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

A Run represents one execution attempt. Modelling retrying as a mutable status on the same Run conflicts with the requirement to preserve failed execution history and make each attempt independently auditable.

## Decision

A Run moves through queued, waiting_for_resources, and running states, then reaches a terminal state: succeeded, failed, cancelled, or timed_out.

A retry creates a new Run with a new run ID, an incremented attempt number, and retry_of_run_id referencing the previous attempt. A terminal Run is not reopened or mutated. The word retrying may appear in orchestration events or policy state, but it is not a Run lifecycle status.

A running Run must identify its start time, worker, and implementation. A succeeded Run must additionally have a finish time.

## Consequences

- Failed attempts remain immutable and inspectable.
- Retry policies operate across Run records rather than rewriting a Run.
- Run IDs and attempt numbers have clear meanings.
- Orchestration must create and link the next attempt explicitly.

## Alternatives considered

- Add retrying as a mutable status of the existing Run: rejected because it blurs execution attempts and weakens historical integrity.
- Reopen a failed Run: rejected because it destroys the distinction between attempts.
