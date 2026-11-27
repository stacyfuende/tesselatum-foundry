# ADR-055: Bounded experiment execution and comparison aggregation

## Status
Proposed for review on PR #24

## Context
Experiment planning expands method and parameter combinations into deterministic variant declarations. Users need to execute those variants through Foundry's existing registered capability services and receive a consolidated report, including partial failure.

## Decision
Add a bounded execution coordinator. It accepts at most 100 planned variants and requires a trusted capability Run callback. It executes each variant independently, records success or failure without aborting the entire experiment, and optionally compares every pair of successful results through a supplied comparison callback.

The coordinator is intentionally capability-service-neutral. It does not evaluate generated code, create workers, authorize sources, or bypass Run lifecycle controls. Those responsibilities remain with the injected Foundry execution service.

## Report
The JSON-compatible report records version, variant count, succeeded/failed counts, each variant's key/method/parameters/status and result or error, and pairwise comparison metrics when requested.

## Boundaries
This is a coordination API, not a persistent Experiment resource, scheduler, concurrency engine, sensitivity analyzer, or scientific interpretation system. Callers are responsible for supplying trusted execution and comparison callbacks and for ensuring their results are JSON-compatible.

## Consequences
A capability-specific integration can now run a bounded experiment and consolidate its outcomes. Pairwise comparison becomes available without making execution capability arbitrary or unbounded.
