# ADR-059: Guarded Product Blueprint handoff to Recipe Runs

- Status: Proposed for review on PR #24
- Date: 2026-11-27

## Context

A deterministic Product Blueprint plan is useful only if it can enter Foundry's existing execution machinery without bypassing capability contracts, typed Cell inputs, spatial validation, or the Run lifecycle. The Blueprint abstraction and the existing Recipe/Cell execution model are intentionally different: the former expresses outcomes and reasoning; the latter is the trusted execution substrate.

## Decision

Introduce a compiler and guarded handoff from a planned Product Blueprint to the existing Recipe Execution Service.

The compiler:

1. Requires a non-blocked plan with no pending explicit approval.
2. Requires a Cell template for every planned reasoning node, pinned to the exact capability version.
3. Constructs deterministic Cell identities from the plan fingerprint and resolved execution inputs.
4. Converts upstream `node.output_port` bindings into typed Cell-output bindings and Recipe graph edges.
5. Requires all other inputs to be resolved to schema-valid immutable Artifact or typed external-source bindings.
6. Verifies that evidence bindings preserve the URI declared by the supplied evidence reference.
7. Requires Cell templates to provide complete output contracts, including CRS and geometry metadata for spatial outputs; capability data kinds and supported geometry/media types are checked.
8. Requires every product output to map to a declared reasoning-node output.
9. Validates the generated Cell and Recipe contracts and checks the Recipe graph before returning the compiled package.

The execution handoff re-plans the original blueprint against the current policy and capability registry. A changed plan fingerprint is rejected. Only plans whose autonomy decisions are all automatic may enter the Recipe Execution Service. Guided and explicit decisions stop before any Run is created.

Before execution, generated Cells and the Recipe are registered in the immutable Versioned Definition Store. The handoff then calls the existing `execute_registered` path, rather than passing ephemeral definitions directly to the runner. A stable factory identity records who created these reusable definitions; the initiating actor ID is still passed to the Run service for execution provenance. The Recipe service remains responsible for canonical capability and implementation conformance, artifact resolution, spatial preconditions, per-Cell Runs, output validation, and Run provenance.

Generated Recipe and Cell IDs include a compilation fingerprint so different resolved inputs or output contracts do not reuse the same execution identity.

## Trust boundary and limitations

- This is a compiler and guarded adapter, not a new execution engine.
- The current adapter does not provide identity, consent capture, or an approval-verification service. It therefore fails closed for guided/explicit work; it does not accept a caller-supplied boolean as approval.
- Input resources must already be resolved into valid Artifact or typed external-source bindings. Source discovery, licensing verification, and evidence freshness resolution are not performed here.
- Cell templates must declare the spatial output CRS and geometry contracts. The existing Recipe spatial validator checks these against resolved inputs before execution.
- Product acceptance checks are carried by the plan but are not yet evaluated by a product-level release service. Successful Cell Runs are not equivalent to an accepted or published product.
- Generated definitions are persisted before execution. If registration is interrupted, unused immutable Cell definitions may remain; no Run begins until the complete Recipe is registered and the registered execution path is invoked.
- This adapter does not package a customer experience, deploy, or publish outputs.

## Consequences

The first executable bridge now exists: a fully automatic, fully resolved Product Blueprint can be compiled into immutable registered Cell/Recipe definitions and handed to the existing registered Recipe Run service. The next milestone is a product-level acceptance and assembly service, followed by a real end-to-end execution against an existing registered worker and immutable input Artifact.
