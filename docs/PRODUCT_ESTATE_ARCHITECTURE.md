# Tessellatum product estate: Microproducts, SiteSelector, Foundry and discovery

**Status:** Strategic architecture decision — proposed integration boundaries  
**Date:** 2026-11-11  
**Purpose:** Prevent product proliferation from creating duplicate backends, competing registries, or disconnected distribution systems.

## 1. Operating principle

Tessellatum should build many focused customer-facing products on top of a small number of reusable capabilities. Products remain independent in their customer experience and commercial positioning; shared infrastructure is centralized only where doing so reduces cost, improves quality, or compounds value.

A product is not required to use every platform. A small calculator should not inherit spatial infrastructure, authentication, a database, or a subscription system without a real need.

## 2. Responsibility boundaries

### Microproducts — customer-facing applications

Own:
- A clearly defined customer job and audience.
- Product UX, onboarding, product-specific settings and user feedback.
- Product-level analytics and conversion events.
- The appropriate pricing and distribution model.
- Product-specific reliability, support and lifecycle decisions.

Do not own:
- Duplicated generic spatial engines, capability contracts or recipe semantics.
- A second copy of shared geospatial datasets or spatial processing infrastructure when an existing service is suitable.
- A bespoke platform stack for every app.

### SiteSelector / GSSE — applied spatial intelligence and domain APIs

The existing GSSE repository already contains a FastAPI backend, a Next.js frontend, geospatial intelligence concepts, a plugin registry, reporting, account/credit and payment flows. Its role should be the applied spatial intelligence service layer.

Own:
- Location- and site-selection domain APIs.
- Domain-specific indicators, scoring, spatial context, geospatial data access and reporting.
- Reusable SiteSelector services that other products can consume when their customer job genuinely requires spatial intelligence.
- Product-facing adapters and domain workflows for SiteSelector itself.

Do not turn SiteSelector into the universal home for every backend API. Generic application services (for example, reminders or invoice tracking) belong with the relevant product or a genuinely shared application service. SiteSelector must not become a second Foundry compute engine.

### Tessellatum Foundry — canonical spatial computation and recipe infrastructure

The current Foundry contracts and implementation remain authoritative for:
- Artifacts and immutable versions.
- Versioned Capabilities and conformance-gated implementations.
- Declarative Geo-Cells.
- Versioned Recipe graphs.
- Runs, execution lineage and Validation Reports.
- Reproducible spatial computation across compatible engines.

A product or SiteSelector service may request a validated Foundry Recipe or capability execution through an authenticated service boundary when that boundary is production-ready. It must not copy Foundry's contracts into a competing private workflow format.

**Important status distinction:** Foundry currently has a local Python SDK and initial local/remote worker paths. Its authenticated multi-tenant network API, generated client SDK and production service boundary are not yet complete. Do not describe it as a generally available hosted API today.

### Tessellatum Distribution & Commerce — acquisition and monetization

Own:
- Product catalogue, public product pages and cross-product discovery.
- Search engine optimization (SEO) and generative engine optimization (GEO).
- Structured product information, indexability, useful documentation, examples and evidence.
- Customer acquisition, conversion measurement, email/newsletter and partner channels.
- Shared checkout, entitlement or delivery infrastructure only where the economics and security justify it.

## 3. Foundry Exchange — marketplace direction

The marketplace direction should be preserved, but separated from Foundry's execution core.

**Working concept: Foundry Exchange** — a discovery, distribution and commercial layer for reusable spatial capabilities, validated Recipes, implementations, data products, specialist services and productized solutions.

The Exchange may also host or connect customers to SEO and generative engine optimization offers that help businesses make their products and expertise easier to discover through Google and AI answer engines.

These are related but distinct jobs:
1. **Marketplace discovery:** help a buyer find, evaluate, acquire and reuse a capability, Recipe, data product, app or service.
2. **Search/answer-engine optimization:** help a publisher or supplier make its own offering understandable, crawlable, citable and discoverable in search and answer experiences.

Do not conflate Foundry's spatial meaning of geospatial with GEO meaning generative engine optimization. Use the full phrase in product copy.

The marketplace is a proposed direction, not a currently implemented Foundry feature. Listing, payment, licensing, moderation, attribution, quality review, seller identity and ranking rules require their own design and evidence. Marketplace rankings must not imply technical conformance or methodological suitability unless those checks have actually been performed.

## 4. How a product should consume the estate

Use this decision path for each new app:

1. Define the customer job and the smallest complete product experience.
2. Identify the minimum external data providers and application services required.
3. If it needs location intelligence, check whether SiteSelector already exposes a suitable domain service. Add a new service only when a real product need justifies it.
4. If it needs reusable spatial computation, express the operation as a Foundry Capability/Geo-Cell/Recipe rather than inventing a parallel workflow model.
5. Keep product-specific orchestration and presentation in the product unless it is demonstrably reusable.
6. Publish a product page with accurate functionality, limitations, data provenance and pricing.
7. Measure acquisition, activation, repeat use, conversion, operating cost and support burden.
8. Promote proven reusable components into shared infrastructure; do not centralize speculative abstractions.

### Example: Aurora Sighting

- **Frontend:** the Aurora Sighting app owns the viewing experience, location input, forecast presentation, user preferences and later alert settings.
- **External data adapters:** geomagnetic forecast, cloud/weather forecast, darkness and relevant location/time data. Provider-specific credentials and reliability remain server-side.
- **SiteSelector:** optional location intelligence only where its existing services add value (for example, place context or location resolution). Do not force aurora forecasting into SiteSelector's site-selection scoring model.
- **Foundry:** reusable spatial/time computations and validated Recipes where a genuine computation graph is needed. Foundry is not a proxy for every external API.
- **Distribution:** the product's own landing page, structured content, search visibility, answer-engine-readable documentation and cross-promotion from Tessellatum.
- **Trust:** distinguish a composite viewing-planning index from a probability of seeing aurora; display source timestamps, forecast horizons and uncertainty. No visibility guarantees.

The current Aurora Sighting frontend is a static visual prototype with sample values. It is not connected to live data, alerts, accounts or billing.

## 5. Product lifecycle and reuse loop

`Customer problem → product → real usage → reusable capability/recipe → documented offer → distribution → more customer problems`

The loop must run in both directions:
- Products reveal which shared capabilities are worth building.
- Shared capabilities reduce the cost and time of future products.
- Recipes become repeatable, inspectable deliverables and potential marketplace inventory.
- Product usage and support reveal demand; marketplace traffic and conversion reveal which offers deserve investment.
- Search/answer-engine content should be generated from verified product facts and useful evidence, not thin programmatic pages.

## 6. Governance rules

- One canonical owner for each contract, dataset, API and capability.
- No shared service without a named owner, documented interface, versioning and operational expectations.
- Product-specific requirements must not silently change shared service semantics.
- Never claim a recipe is validated, a provider is live, or an app is production-ready without corresponding tests and runtime evidence.
- Keep user data, provider credentials and sensitive operational information out of public catalogue pages.
- Prefer a small number of proven shared services over a large speculative platform.
- A product earns its place through customer value, revenue, audience, strategic distribution or measurable reuse. Retire products that do not earn their maintenance cost.

## 7. Immediate sequence

1. Keep the Aurora Sighting frontend prototype isolated from production product navigation until its experience and data contract are validated.
2. Inspect SiteSelector's existing API surface and identify reusable location/context endpoints before adding new ones.
3. Continue Foundry's engineering roadmap independently; do not interrupt contracts, conformance and execution hardening to build marketplace UI.
4. Design Foundry Exchange as a separate marketplace/discovery layer with a clear data model and truthful quality signals.
5. For each next microproduct, write a one-page dependency map before implementation. Reuse only what the product actually needs.
