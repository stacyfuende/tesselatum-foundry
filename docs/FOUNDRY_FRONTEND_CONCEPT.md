# Foundry Product Experience

**Product direction:** an autonomous spatial product factory. Foundry is not a GIS desktop, spatial notebook, or toolbox with a conversational layer.

The customer expresses an outcome. Foundry resolves evidence, plans and executes registered capabilities, assembles a product, validates it, and publishes or operates it. The interface exposes consequential decisions and useful results; implementation mechanics remain inspectable but do not define the default workflow.

## Product principles

1. **Outcome before instrument.** Start with what someone needs to decide, understand, communicate, deliver, or monitor. Do not start with a project, layer, algorithm, or file.
2. **Hide mechanics, not consequences.** Routine reversible operations are automatic. Material assumptions and trade-offs are surfaced. High-impact, costly, sensitive, or irreversible actions require authorisation.
3. **Evidence before assertion.** Every material result can be traced to source evidence, transformations, methods, parameters, versions, validation, and known limitations.
4. **Capabilities, not tool menus.** The engine composes registered, typed, bounded capabilities. It never executes arbitrary LLM-generated code.
5. **Products, not projects.** The durable customer object is a product instance with releases, artefacts, evidence, and an operational lifecycle.
6. **Presentation is a discipline.** Cartography, documents, applications, APIs, and monitoring have their own specifications and quality criteria. They are not generic exports.
7. **Progressive agency.** Foundry acts automatically where safe, guides decisions where judgement matters, and asks permission where consequences demand it.
8. **No silent magic.** Record decisions, uncertainty, limitations, resource budgets, and failures. A polished output must not conceal weak evidence.

## The six conceptual boundaries

These are responsibilities in one platform, not six separate applications:

- **Intent:** desired outcome, question, decision, audience, constraints, and success conditions.
- **Evidence:** source references, observations, measurements, derived facts, freshness, coverage, rights, quality, uncertainty, and provenance.
- **Reasoning:** registered methods, algorithms, models, assumptions, comparisons, constraints, and sensitivity.
- **Product:** the useful deliverable or ongoing service, described independently of its presentation.
- **Experience:** how the product is consumed: cartography, document, application, API, or other interface and medium.
- **Operation:** publishing, releases, refreshes, monitoring, alerts, feedback, and retirement.

## What is deliberately not the user-facing architecture

The following may remain useful internal representations or expert inspection tools, but they are not primary customer concepts:

| Legacy convention | Foundry treatment |
|---|---|
| GIS project | Product context and working state |
| Layer tree | Evidence and spatial resources |
| Processing toolbox | Registered capability catalogue |
| Processing model | Typed, versioned recipe/plan |
| Manual CRS dialog | Spatial reference resolution with recorded rationale |
| Manual map layout workflow | Cartographic specification and composition engine |
| Geoprocessing history | Execution provenance and product lineage |
| Export wizard | Product release and delivery |
| Repeated manual updates | Product operation policy |
| Project file as the deliverable | Product instance, releases, and artefacts |

Do not delete useful algorithms, data structures, or expert controls merely because their historical interface is being retired. Preserve sound computation; replace the interaction model and abstractions around it.

## Autonomy model

Every consequential decision is classified by impact, reversibility, uncertainty, cost, sensitivity, and user preference.

- **Automatic:** routine, bounded, reversible choices with acceptable confidence. Execute and record the decision.
- **Guided:** choices that materially affect interpretation or quality. Recommend a default, explain trade-offs, and support alternatives or sensitivity tests.
- **Explicit authorisation:** high-impact, irreversible, legally significant, privacy-sensitive, externally published, or materially costly actions.

The classification is contextual. A projection may be automatic for a small local map but require guidance for a continental analysis. A colour choice may be cosmetic in one context and misleading in another. Never classify a decision solely by whether it looks technical.

## Product creation lifecycle

1. **Understand** — resolve intent, audience, constraints, success criteria, and missing information.
2. **Resolve** — discover and assess evidence, rights, coverage, freshness, quality, and feasibility.
3. **Plan** — select registered capabilities, methods, product specifications, autonomy decisions, and budgets.
4. **Build** — execute through trusted Foundry Run services.
5. **Validate** — test evidence, computation, product-specific quality, and declared acceptance criteria.
6. **Assemble** — produce the appropriate experience and delivery artefacts.
7. **Release** — publish or deliver a versioned product with provenance.
8. **Operate** — refresh, monitor, alert, revise, and retire under an explicit policy.

The planner may reuse valid prior work. Changes should invalidate and rebuild only affected dependencies when lineage and contracts prove that reuse is safe.

## Product surfaces

The default application has three destinations:

### Create
A natural-language and structured entry point for describing the intended outcome. Foundry asks only consequential questions. It previews the resolved plan, assumptions, costs, and permissions before execution where needed.

### Products
A catalogue of product instances, not a list of GIS projects. Each product has a preview, purpose, release history, status, evidence, and available actions.

### Engine
An expert surface for evidence sources, capabilities, methods, recipes, experiments, Runs, artefacts, validation, budgets, and provenance. It is available when needed and never required for ordinary product creation.

The product itself gets the interface appropriate to its purpose. A cartographic publication should not be forced into a dashboard shell; an interactive decision tool should not be forced into a static map layout.

## Product and experience specifications

A general Product Blueprint defines intent, evidence requirements, reasoning graph, constraints, autonomy policy, acceptance criteria, and one or more product outputs.

Specialised specifications define how a product is realised:

- **Cartographic specification:** audience, communication purpose, geography, projection, scale, physical dimensions, medium, resolution, layers, symbolisation, typography, labels, legend, annotations, composition, accessibility, and export targets.
- **Document/dossier specification:** narrative structure, evidence requirements, citations, tables, figures, page geometry, audience, and publication format.
- **Application specification:** user tasks, information architecture, interactions, permissions, responsive behaviour, and deployment target.
- **Service specification:** contract, interface, authentication, latency/resource expectations, versioning, and availability.
- **Operational specification:** refresh triggers, monitoring conditions, alert policies, retention, and service-level expectations.

A specification is declarative and validated. Rendering and execution are performed by registered engines, not by arbitrary generated scripts.

## Quality and trust

Validation is layered:

- Evidence validity: source identity, access, rights, freshness, coverage, and data quality.
- Computational validity: capability conformance, parameter constraints, budgets, deterministic/reproducible behaviour where promised.
- Product validity: whether the output satisfies its declared purpose and acceptance criteria.
- Experience validity: legibility, accessibility, layout integrity, responsive behaviour, and interaction correctness where applicable.
- Operational validity: release integrity, refresh behaviour, monitoring, and rollback/retirement controls.

A product cannot be labelled successful merely because computation completed. Product-specific acceptance checks must pass or be clearly reported as incomplete.

## Interface direction

- Quiet, precise, editorial, and outcome-oriented; warm neutral/graphite foundations with restrained terracotta accent.
- Lead with product previews and decisions, not maps as wallpaper or technical dashboards.
- Use the right medium for the job: maps, charts, tables, reports, interfaces, and evidence views are complementary.
- Make expert detail discoverable, not compulsory.
- Keyboard accessible, responsive, semantic, readable, and usable without colour-only status.
- No generic AI sparkle motifs, decorative progress, or fabricated success states.

## Implementation sequence

1. Establish the architecture decision and the general Product Blueprint contract.
2. Define autonomy/decision policy and capability declarations.
3. Implement planning and dependency validation without arbitrary code execution.
4. Connect plans to real Run services and product artefact packaging.
5. Implement the Cartographic Specification and a real cartographic rendering/QA path.
6. Deliver one end-to-end flagship spatial product.
7. Add further experience engines only as required by real product jobs.
8. Build the Create / Products / Engine frontend on top of proven services.

## Current implementation boundary

The branch contains working bounded external raster access, a live Nairobi Sentinel-2 execution proof, raster window processing and validation, experiment planning/execution primitives, and raster comparison. Those are valuable engine capabilities, not a complete product factory.

The general Product Blueprint, autonomy engine, product planner integration, cartographic engine, publishing/operations system, and customer-facing frontend remain to be implemented. Do not present a concept, schema, or callback seam as an end-to-end product capability.
