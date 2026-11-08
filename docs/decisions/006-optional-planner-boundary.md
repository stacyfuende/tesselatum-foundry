# ADR-006: The planner is optional and outside the execution core

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Natural-language planning can make Foundry easier to use, but probabilistic planning must not become a dependency of deterministic execution.

## Decision

The execution core accepts a fully specified, validated Recipe. A planner may propose a Recipe from natural language, templates, or other context, but it is replaceable and is not required to validate, schedule, or execute a valid Recipe.

All planner-produced objects pass the same schema, semantic, authorization, and policy gates as API-created objects. The planner cannot bypass validation or directly invoke arbitrary execution tools.

## Consequences

- The core remains usable without an LLM.
- Planner implementations can be replaced independently.
- Proposed workflows must be inspectable and attributable to their source.
- Human confirmation and policy gates can be added for high-impact operations without changing execution semantics.

## Alternatives considered

- Agent as primary orchestrator: rejected because it couples correctness to probabilistic behaviour.
- No planner extension point: rejected because it would unnecessarily constrain future interfaces.
