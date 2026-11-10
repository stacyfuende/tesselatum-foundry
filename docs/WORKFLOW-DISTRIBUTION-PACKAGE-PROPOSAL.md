# Workflow Distribution Package — Design Proposal

**Status:** Proposed; no runtime implementation or public distribution is implied.  
**Last reviewed:** 2026-11-10  
**Scope:** A portable, versioned bundle for distributing and licensing reusable Foundry Recipes.  
**Non-goals:** Marketplace, payment processing, remote package installation, public registry, arbitrary code plugins, or a production hosted execution service.

## 1. Decision

Keep the canonical **Recipe** contract focused on computation graph semantics. Do not add commercial packaging, seller identity, pricing, licence text, screenshots, or distribution metadata directly to `schema/recipe.schema.json`.

Introduce a separate **Workflow Distribution Package** envelope. It packages an immutable Recipe and the exact dependencies and evidence needed to validate, understand, and execute it in a compatible Foundry environment.

This separation preserves the architectural invariant that a Recipe is a versioned DAG of Geo-Cells, not a commercial product listing or an execution.

The package is a distributable unit. A Recipe is the computation graph inside it.

## 2. Why this boundary matters

A Recipe alone is not necessarily executable by another user:
- its referenced Cell versions may not be available;
- required Capability contracts may be missing;
- no compatible, conformance-passed implementation may be installed;
- its input Artifacts may be private, unavailable or licensed separately;
- the receiver may not have the correct runtime or resource budget;
- its methodological limits may not be understood.

A workflow package must make these dependencies explicit without changing the canonical execution model.

## 3. Package contents

A package should be a deterministic archive (initially ZIP) with a canonical manifest and content checksums.

Suggested layout:

```text
workflow-package/
  manifest.json
  recipe.json
  cells/
    <cell-id>/<version>.json
  capabilities/
    <capability-id>/<version>.json
  implementation-requirements.json
  validation/
    package-validation.json
    test-cases/
  examples/
    inputs/
    expected/
  documentation/
    README.md
    methodology.md
    data-requirements.md
    limitations.md
    changelog.md
  licences/
    workflow-license.txt
    third-party-notices.txt
  checksums.sha256
```

The archive MUST NOT contain executable worker code in v1. It describes and pins compatible implementations; it does not smuggle arbitrary code into a trusted execution environment.

Input data should be included only when it is synthetic, public and licensed for redistribution, or explicitly permissioned. Otherwise, package a schema and acquisition instructions, not the customer's dataset or a private provider payload.

## 4. Manifest contract

The manifest is separate from the Recipe schema and should be versioned independently. Initial conceptual fields:

| Field | Purpose |
|---|---|
| `package_id` | Stable package identity |
| `package_version` | Immutable semantic package version |
| `title`, `summary`, `description` | Human-readable product description |
| `publisher` | Publisher identity and contact route |
| `recipe_ref` | Exact Recipe ID, version and checksum |
| `cell_refs` | Exact Cell IDs, versions and checksums |
| `capability_refs` | Exact Capability IDs, versions and checksums |
| `implementation_requirements` | Compatible implementation IDs/versions and conformance expectations; no automatic substitution |
| `input_contracts` | Required external Artifact metadata, media types, CRS/units and size constraints |
| `output_contracts` | Named outputs, expected media types and spatial metadata |
| `runtime_requirements` | Supported Foundry SDK/runtime range and resource ceilings |
| `validation_evidence` | Test suite identity, version, coverage and last verified environment |
| `rights` | Package licence, third-party notices, data-use constraints and declarations |
| `provenance` | Source revision, build identity and package creation time |
| `commercial` | Optional catalogue metadata; price and purchase entitlements are managed outside the package |

The manifest MUST NOT contain credentials, secret URLs, bearer tokens, private file paths, live customer records or mutable aliases such as `latest`.

All dependencies MUST be pinned to immutable versions and checksums. A missing dependency is a validation failure, not a reason to silently fetch a different version.

## 5. Package lifecycle

1. **Author:** Create and validate a Recipe and its Cell definitions.
2. **Resolve:** Enumerate exact Capability versions, required implementations, input contracts and declared outputs.
3. **Test:** Execute deterministic examples in a clean supported environment; retain validation reports.
4. **Review:** Inspect data rights, methodology, security, resource limits and documentation.
5. **Build:** Assemble a deterministic archive and checksums.
6. **Verify:** Extract the archive into a clean environment and validate all references, schemas, checksums and test fixtures.
7. **Publish:** Release an immutable package version to a controlled catalogue or private distribution channel.
8. **Support:** Publish compatibility, issue, update and deprecation policy.
9. **Revise:** A material change creates a new package version; previously distributed versions remain identifiable.

## 6. Import and execution safety

The first importer should be a local SDK/CLI capability, not a public upload endpoint.

Before execution it MUST:
- reject path traversal and unsafe archive entries;
- enforce compressed and expanded size limits;
- verify all checksums;
- validate every JSON document against the installed canonical schema;
- resolve exact Cell, Capability and Recipe references;
- confirm compatible conformance-passed implementations are installed;
- verify required external inputs and metadata;
- report missing rights declarations as unknown, not permitted;
- inspect declared resource limits;
- require explicit operator approval before executing a newly imported package.

Importing a package MUST NOT automatically execute it, install executable code, access external URLs, or grant access to private data.

## 7. Trust and evidence model

A package can make claims only about evidence included and verified:
- structural and semantic Recipe validity;
- exact dependency availability;
- conformance status of referenced implementations;
- test cases actually executed;
- output checks actually performed;
- runtime/environment used for verification;
- known methodological and data limitations.

A passing package test does not establish that a workflow is suitable for every geography, dataset, purpose or regulatory context. Suitability and legal permission remain separate assessments.

Publisher identity and archive checksums provide integrity context, not proof that a workflow is safe or analytically correct. A future signing mechanism may authenticate publisher-controlled releases, but must not be represented as implemented in this proposal.

## 8. Commercial packaging

A distributable workflow is more valuable when sold as a complete operational asset rather than a bare graph.

Possible offers:
- **Workflow package licence:** permission to use one immutable package version.
- **Workflow + implementation:** package plus a supported compatible runtime/worker.
- **Configured deployment:** package installed and tested against the customer's environment and inputs.
- **Maintained workflow subscription:** version updates, compatibility testing and support for a defined period.
- **Done-for-you result:** Tessellatum runs the workflow and delivers a reviewed outcome; customer need not operate Foundry.

The package should not embed price or customer entitlements. Those belong to a future catalogue, order and licensing system. A private distribution can be sold manually before building a marketplace.

## 9. Versioning rules

- Recipe changes create a new Recipe version.
- Cell semantic changes create a new Cell version.
- Capability semantic changes create a new Capability version.
- Implementation changes create a new implementation version and require the relevant conformance evidence.
- Package metadata/documentation changes create a new package version even when the underlying Recipe is unchanged.
- A package version is immutable after publication.
- A security or rights issue may cause a package to be withdrawn from new distribution, but historical order records and customer obligations remain explicit.
- Compatibility is declared as a tested range; never infer compatibility from a package's age or a matching operation name.

## 10. Implementation sequence

### Phase 0 — documentation and manual package build
- Define manifest schema and archive layout.
- Build one package manually from a simple, already-supported Recipe.
- Verify extraction, checksums, schema validation and local execution in a clean environment.
- Record what is missing.

### Phase 1 — local packaging tools
- Add deterministic package builder and verifier.
- Add safe archive extraction.
- Add package validation reports.
- Add local SDK/CLI import without automatic execution.

### Phase 2 — private distribution
- Store immutable packages in controlled object storage.
- Record package version, publisher, licence, checksum and download entitlements.
- Start with manual invoicing/licensing and supported customer onboarding.

### Phase 3 — commercial catalogue
- Add product pages, checkout, entitlement, download, updates and support workflows.
- Introduce only after customer demand and support cost are demonstrated.

### Phase 4 — execution service
- Add authenticated multi-tenant API, quotas, isolation, observability, cost accounting and customer-specific data controls.
- Treat this as a separate major readiness gate; a downloadable package does not imply hosted execution is available.

## 11. First package candidates

Only use capabilities that are already integrated and verified in the exact Foundry release being packaged.

- **Vector Buffer Preparation:** explicit planar buffer workflow using a supported projected measurement CRS and declared units.
- **Vector Reprojection & Evidence:** transformation with operation metadata and area-of-use coverage evidence, with limitations stated.
- **Simple sequential buffer → reproject Recipe:** only if the exact mixed Recipe, implementation pins, clean install and validation reports are reproducible.

Raster band statistics remains under review in the project status tracker; do not use it as the first distributable package until its CI and full Run/Artifact/Recipe integration gates pass.

## 12. Acceptance criteria for v1 package format

- [ ] Manifest has a published JSON Schema and version.
- [ ] One deterministic package can be built twice with identical content checksums.
- [ ] Archive verifier rejects modified/missing files and path traversal.
- [ ] All Recipe/Cell/Capability references resolve to exact immutable versions.
- [ ] Package import does not execute code or access the network.
- [ ] Missing implementation or input dependency fails clearly.
- [ ] Clean-environment example executes with the declared local SDK.
- [ ] Validation evidence is included and tied to exact package contents.
- [ ] Rights and data redistribution rules are explicit.
- [ ] A human can understand the workflow, inputs, outputs, limitations and support terms without reading source code.

**Recommendation:** Build the package format only after the current local SDK and Recipe execution are stable enough to support a clean-environment test. Do not prioritise marketplace UI, public package hosting or payment integration ahead of this boundary.
