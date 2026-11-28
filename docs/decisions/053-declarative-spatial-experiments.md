# ADR-053: Declarative spatial experiments and method comparison

- **Status:** Accepted
- **Date:** 2026-11-27

## Context

A spatial computation should be interrogable and repeatable: users and LLMs may compare methods, change parameters, test thresholds, reproduce a paper, or vary one assumption while holding others fixed. Existing Runs and immutable Geo-Cells already provide execution and provenance primitives, but there is no declaration for a bounded experiment that expands method alternatives and parameter axes into comparable variant plans.

## Decision

Add a versioned Experiment manifest and deterministic planner. The manifest records the objective, Cell template, baseline parameters, parameter axes, method alternatives, capability overrides and method evidence references (papers, documentation, benchmarks or user notes).

The planner expands method alternatives × parameter-axis Cartesian products into Cell variants. It preserves baseline values, applies method overrides, then axis overrides; each resulting plan receives a stable SHA-256 identity derived from the experiment/version, method, capability, Cell template and effective parameters. Duplicate definitions and expansions above the explicit limit (default 50, hard maximum 100) are rejected.

The planner is declarative and does not run code. Actual execution is delegated to exact registered Capability/Run services. It never executes LLM-generated scripts, fetches paper code, or trusts a paper reference as executable authority.

## Consequences

- A user can request comparisons, sweeps, method alternatives and paper-grounded variants in one manifest.
- Identical experiment declarations produce identical variant keys.
- The exact effective parameters and evidence references travel with every variant plan.
- The planner is safe to expose to an LLM because it creates bounded declarations, not arbitrary code execution.
- Result aggregation, metric selection, actual multi-variant orchestration, and spatial method implementations remain subsequent work.
