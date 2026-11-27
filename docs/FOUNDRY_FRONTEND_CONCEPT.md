# Foundry Frontend Concept

**Product direction:** a spatial computational laboratory, not a traditional GIS desktop, notebook, or monitoring dashboard.

Foundry's interface is organized around the user's question and the experiment—not around a layer list. The conversational assistant is the front door, while the computation workspace makes the underlying methods, parameters, data, evidence, runs, and outputs inspectable.

## Design principles

1. **Question-first.** Start with "What are you trying to find out?" rather than asking users to configure a GIS project.
2. **Conversation + workspace.** Chat is not the entire interface. Every consequential suggestion can open a structured experiment, data inspection, method comparison, or result view.
3. **Inspectable computation.** A user can inspect the selected source, method, parameter values, evidence, cell declaration, run status, validation, and provenance.
4. **Experiment as first-class object.** Variants, baselines, parameter sweeps, comparison metrics, and failure cases are visible together.
5. **Maps are evidence, not wallpaper.** Map and imagery views appear when spatial context materially matters; charts, tables, distributions, and explanations are equally important.
6. **Progressive complexity.** Beginners can ask in natural language. Experts can open the method panel, edit parameters, inspect the manifest, and access reproducibility details.
7. **No silent magic.** Unsupported operations, transformations, data access limits, uncertainty, and execution failures are stated.

## Primary application shell

Desktop: three working zones, with a slim global navigation rail.

- **Left rail (56–72 px):** Foundry mark; New investigation; Experiments; Data sources; Methods; Runs; Artifacts; settings/account.
- **Main work area:** conversation or active experiment. A top title strip shows the investigation and its status.
- **Context panel (about 320 px, collapsible):** selected source, methods, parameter controls, provenance, and experiment details. This panel changes with the active task.

On mobile, the rail becomes bottom navigation; context and comparison panels become full-screen sheets. The experiment remains usable without desktop-only hover behavior.

## Screen 1 — Foundry home / investigation

A quiet, editorial interface with a large prompt, recent work, and a few concrete starting examples.

**Prompt:** "What do you want to investigate?"

Examples:
- Compare two ways to estimate a surface from observations.
- Test how a site-selection score changes when the weights change.
- Find a suitable external dataset for this question.
- Reproduce a method described in a paper.

Recent investigations show a short title, last activity, state, and the number of Runs or artifacts. Avoid noisy dashboard widgets.

## Screen 2 — Investigation workspace

```
┌─ Foundry ──────────────────────────────────────────────────────────────┐
│ Investigation: Nairobi vegetation signal                       Saved │
├─────────────┬─────────────────────────────────────┬──────────────────┤
│ Conversation│ Active work                         │ Inspector        │
│             │                                     │                  │
│ User asks   │  Data source                        │ Source details   │
│ a question  │  Sentinel-2 / red band               │ Provider         │
│             │       ↓                              │ Asset / date     │
│ Assistant   │  Experiment                          │ CRS / resolution│
│ explains    │  baseline + variants                 │ Access budget   │
│ choices     │       ↓                              │                  │
│             │  Compare results                      │ Method details   │
│ Follow-up   │  Map / chart / metrics / table       │ Parameters      │
│ prompts     │                                     │ Provenance      │
├─────────────┴─────────────────────────────────────┴──────────────────┤
│ [Ask a follow-up…]                         [Run experiment]          │
└─────────────────────────────────────────────────────────────────────┘
```

The conversation can ask clarifying questions, explain a method, suggest alternatives, or interpret evidence. The structured workspace is the durable state: experiment definition, selected data, variants, and outputs. The assistant should not pretend a run occurred merely because it described one.

## Screen 3 — Data/source explorer

Sources are represented as reference cards, not as Foundry-owned copies.

Each source card exposes:
- Provider and source URL/identifier.
- Dataset/item/asset selection.
- Spatial and temporal extent.
- CRS, resolution, bands/fields, and data type where discoverable.
- License/access constraints when available.
- Estimated bounded-read size and Foundry's actual access budget.
- Availability/health check with timestamp.
- Provenance and reproducibility caveats.

The source picker should search supported catalogs, allow a URL or STAC reference, and show a preview/metadata before adding it to an experiment. Source access and actual reads remain controlled by Foundry's backend contracts.

## Screen 4 — Method laboratory

A method is a card with a plain-language explanation and a technical expansion.

Card content:
- Method name and what it estimates/does.
- When it is appropriate.
- Assumptions and limitations.
- Required inputs.
- Parameters with units, allowed ranges, defaults, and sensitivity guidance.
- Implementation/engine and conformance status.
- Evidence links (paper, docs, benchmark, or user-provided source).

Users can choose "Use this method", "Compare", or "Inspect". For paper-based work, evidence is attached to the method/experiment, and the system clearly distinguishes the paper's documented procedure from Foundry's implementation.

## Screen 5 — Experiment builder

An experiment has a baseline, method alternatives, and parameter axes. The UI should visually show how many variants will be generated and prevent unbounded expansion.

Example:
- Baseline: method X, threshold 0.4.
- Method alternatives: X / Y.
- Parameter axis: threshold 0.2, 0.4, 0.6.
- Total: 6 variants.
- Run budget and source budget are visible before execution.

Parameter controls are generated from capability schemas where possible. Advanced users can inspect/edit the declarative manifest. No free-form LLM-generated scripts are executed.

## Screen 6 — Experiment results

A result view has four synchronized sections:

1. **Summary:** what was tested, run status, best-supported observations, and warnings.
2. **Comparison:** metrics table, method/parameter matrix, and difference plots.
3. **Spatial view:** map, imagery, result overlay, or difference view where the output supports spatial visualization.
4. **Evidence & reproducibility:** source references, method/capability versions, exact parameters, Run IDs, validation report, artifacts, timestamps, checksums, and known limits.

The comparison view should make it easy to switch between:
- Side-by-side variants.
- Baseline vs selected variant.
- Difference/overlap.
- Metric table.
- Parameter sensitivity chart.

Metrics must not be presented as universal quality scores; the user chooses/understands the comparison criteria.

## Screen 7 — Run detail

Run lifecycle timeline: queued → resolving inputs → executing → validating → succeeded/failed.

Each step shows events, resource/access budgets, relevant warnings, and outputs. Failed variants are preserved and displayed beside successful variants so partial experiments remain informative. Re-run and clone controls create new Run records; they do not mutate old results.

## Visual language

- **Foundation:** warm neutral / light parchment or soft graphite, restrained borders, spacious layout.
- **Accent:** burnt terracotta/orange for active action and selected states; use sparingly.
- **Typography:** strong modern sans for UI; optional compact monospace for IDs, parameter values, manifests, and provenance.
- **Visuals:** crisp data displays, quiet map backgrounds, clear legends, purposeful charts; no excessive glassmorphism, gradient blobs, or generic AI sparkle motifs.
- **Motion:** short, purposeful state transitions; no decorative loading loops. Execution status uses explicit progress and event activity.
- **Accessibility:** keyboard-first navigation, semantic controls, contrast, no color-only status, reduced motion, and chart/table equivalents.

## Initial implementation sequence

1. App shell, investigation list, responsive navigation.
2. Investigation workspace with chat placeholder and durable experiment state.
3. Source explorer and metadata/source cards.
4. Experiment builder from the current Experiment schema and planner.
5. Run detail using real Foundry Run lifecycle/events.
6. Result comparison and artifact viewer, initially for the supported raster-window artifact.
7. Connect conversational planning to registered capabilities only; the LLM proposes/edits declarations, backend validates, and execution goes through registered Run services.

## Scope honesty

This document describes the intended frontend experience. The current branch has backend computation, external raster access, experiment planning, bounded experiment execution, and exact-grid raster comparison foundations. It does **not** yet contain this frontend, a production hosted API, a general method catalogue, arbitrary paper reproduction, or universal raster visualization. The first frontend slice should be wired to the capabilities and Run lifecycle that actually exist.
