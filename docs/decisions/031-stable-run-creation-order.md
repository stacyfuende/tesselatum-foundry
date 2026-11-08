# ADR-031: Preserve Run creation order independently of timestamp precision

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Run timestamps currently use second-level precision. Multiple Runs created during one Recipe execution can therefore share the same created_at value. Sorting tied Runs by random Run ID does not preserve their actual creation order and can return Recipe node history in an arbitrary sequence.

Creation order is a property of the control-plane record, not something that can safely be reconstructed from UUIDs or filesystem directory iteration.

## Decision

1. Assign each newly created local Run a monotonically increasing creation_sequence while holding the RunRepository write lock.
2. Persist creation_sequence in the Run record and treat it as immutable provenance.
3. Continue accepting legacy Run records without creation_sequence. Their historical order cannot be reconstructed; they remain ordered by timestamp and the existing stable fallback.
4. Sort Run listings by created_at, then creation_sequence, then Run ID. The sequence resolves timestamp ties without changing chronological grouping across timestamp boundaries.
5. Continue documenting that the JSON-backed repository provides single-process concurrency control only. A database-backed repository must allocate this sequence transactionally or replace it with a database-native ordering mechanism.

## Consequences

New Runs created within the same timestamp second are listed in their actual creation order. Recipe Run listings now reliably reflect the sequence in which node Runs were persisted.

The sequence is local repository metadata, not a global distributed clock and not a substitute for event timestamps.

## Alternatives considered

- Increase timestamp precision only: rejected as the sole solution because timestamp collisions remain possible.
- Sort by Recipe node order: rejected as the general Run-listing rule because Runs may not belong to a Recipe and retries or separate executions need a consistent repository-wide order.
- Sort by Run ID: rejected because identifiers are not chronological.
