# ADR-028: Require current complete validation evidence for cache reuse

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The deterministic execution cache reuses an immutable output Artifact only when a prior Run has succeeded, the Artifact metadata is compatible, its content checksum verifies, and a successful execution-output Validation Report exists.

A successful report alone is insufficient evidence. The validator implementation and its assessed dimensions can evolve. Reusing an output assessed by an older validator, or by a report missing one of the current contract checks, would allow stale or incomplete evidence to authorize a cache hit.

The cache key already identifies the output validator name and version. The reuse gate must enforce the same identity against the source report and verify that the expected checks were actually recorded as passed.

## Decision

1. Define one canonical output-validator name and version in the execution service. Use those constants both in the cache-key material and in newly generated output Validation Reports.
2. A cache candidate MUST have a source output Validation Report whose validator name and version exactly match the current output validator.
3. The source report MUST contain every required output finding, and every required finding MUST have status passed.
4. The source report MUST declare all dimensions required by the current output critic as assessed.
5. A candidate with stale, missing, incomplete, or failed validation evidence is a cache miss. The service MUST continue searching other candidates and, if none qualifies, execute the worker normally.
6. This gate does not claim to assess methodological suitability or rights/security policy. Those dimensions remain explicitly unassessed until their dedicated validators exist.

## Consequences

Cache reuse is coupled to the actual validator evidence, not merely to a cache-key string or a top-level passed status. When output-validation semantics change, the validator version must be advanced; old reports will then be ineligible for reuse.

The fallback is correctness-first: rejected cache evidence costs execution time but does not silently authorize reuse.

## Alternatives considered

- **Trust only the report's overall status:** rejected because it does not establish validator identity or completeness.
- **Re-run the full geometry critic on every cache hit:** deferred. It would reduce the performance benefit of caching and should be considered as a separate policy when validator cost and cache trust boundaries are better understood.
- **Treat missing evidence as a warning:** rejected because a cache hit is an execution result and must not be authorized by incomplete evidence.
