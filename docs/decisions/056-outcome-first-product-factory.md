# ADR-056: Outcome-first spatial product factory

## Status
Proposed for review on PR #24

## Context
Foundry has established bounded spatial data access, computation, validation, and experiment primitives. These are necessary infrastructure but do not define the customer product. Continuing to organise the platform around GIS projects, layers, processing tools, and experiment workspaces would reproduce historical GIS interaction patterns and make users assemble machinery manually.

The product direction is an autonomous spatial product factory: a user expresses an outcome; Foundry resolves evidence, reasons over registered capabilities, creates and validates a product, and publishes or operates it.

## Decision
Organise the architecture around six conceptual responsibilities:

1. **Intent** — desired outcome, decision, audience, constraints, and acceptance criteria.
2. **Evidence** — source references, observations, measurements, derived facts, rights, freshness, quality, uncertainty, and provenance.
3. **Reasoning** — registered methods, algorithms, models, assumptions, comparisons, and sensitivity.
4. **Product** — the useful deliverable or ongoing service, independent of its presentation.
5. **Experience** — the cartographic, document, application, API, or other presentation and delivery form.
6. **Operation** — release, refresh, monitoring, alerts, feedback, and retirement.

These are responsibilities in one platform, not separate products or mandatory user-facing modules.

A general Product Blueprint declares intent, evidence requirements, reasoning graph, constraints, autonomy policy, acceptance criteria, and output products. Specialised experience specifications define how a product is presented or delivered. Registered engines execute those specifications.

## Autonomy and control
Foundry classifies decisions contextually:
- **Automatic:** bounded, reversible, low-impact decisions with acceptable confidence; execute and record.
- **Guided:** material interpretive or quality choices; recommend, explain trade-offs, and permit comparison.
- **Explicit authorisation:** high-impact, irreversible, legally significant, privacy-sensitive, externally published, or materially costly actions.

Classification depends on impact, reversibility, uncertainty, cost, sensitivity, and user preference—not whether a choice appears technical. No consequential choice is silently discarded. Decisions and rationale are recorded.

## What is not a primary user abstraction
GIS projects, layer trees, processing toolboxes, processing models, manual CRS dialogs, layout designers, geoprocessing history, and export wizards may remain useful internal representations or expert tools. They do not define the default customer journey.

Preserve sound algorithms and data structures. Replace legacy interaction patterns only where the new abstraction is clearer and safer. Do not discard a capability merely because its old interface is retired.

## Execution and trust boundaries
- LLMs may interpret intent, propose plans, explain trade-offs, and coordinate.
- Only registered, versioned, typed capabilities may perform computation.
- Plans are validated and bounded before execution.
- Execution goes through Foundry Run services; generated arbitrary code is never executed.
- Evidence, assumptions, parameters, resource budgets, provenance, validation, and limitations remain inspectable.
- A successful Run is not equivalent to a successful product. Product-specific acceptance checks must pass or be reported incomplete.

## Product lifecycle
Understand → Resolve → Plan → Build → Validate → Assemble → Release → Operate.

Dependency-aware reuse is permitted only when lineage and contracts prove that prior results remain valid. Changes should invalidate only affected dependencies when safe.

## Initial product surfaces
- **Create:** express an outcome and resolve consequential questions.
- **Products:** inspect product instances, previews, releases, evidence, and status.
- **Engine:** inspect sources, capabilities, methods, recipes, experiments, Runs, artefacts, budgets, and provenance.

The product's own experience must suit its purpose; not every product is a dashboard or map.

## Consequences
This direction makes product specifications, autonomy policy, planning, validation, and packaging first-class engineering concerns. Existing raster and experiment work becomes reusable engine capability. The next milestone is a declarative Product Blueprint and validated planner, followed by a real Run integration and one end-to-end product.

## Non-goals
This decision does not claim a functioning autonomous product factory, cartographic renderer, general source catalogue, publication platform, or production frontend. Those remain implementation work.
