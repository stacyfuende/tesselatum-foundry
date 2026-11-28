# ADR-060: Product acceptance and manifest assembly

- Status: Proposed for review on PR #24
- Date: 2026-11-28

## Context

Recipe success proves that the registered computation completed and declared outputs were produced. It does not prove that the product satisfies every customer-facing requirement. Product Blueprint acceptance checks must be evaluated independently and must never be silently inferred from natural-language descriptions.

## Decision

Add a deterministic product acceptance evaluator with a deliberately small registered validator set:

- `runs.succeeded`: Recipe and every recorded node Run succeeded.
- `outputs.present`: all declared Recipe outputs exist in the result map.
- `artifacts.metadata_valid`: output records include identity/version, SHA-256 checksum metadata, and storage URI.
- `artifacts.checksum_verified`: verify each output's bytes against recorded checksum and size using the supplied Artifact Store.

Checks without one of these exact validator IDs remain `unassessed`. Required unassessed checks place the product in `review_required`; they do not pass. Required failures or failed execution reject the product. Optional failures can produce warnings without blocking acceptance. Acceptance only reports `release_allowed`; it does not publish or deploy.

The assembler creates a manifest recording Blueprint identity, plan and compilation fingerprints, Recipe reference, execution ID/status, per-node Run provenance, output Artifact references/checksums/rights/spatial metadata, and acceptance results. The manifest fingerprint is computed over canonical JSON. The assembler has no external side effects.

## Boundaries

- Validator semantics are code-registered and explicit; check descriptions are never interpreted as executable validation logic.
- This first validator set does not test geometry validity, cartographic quality, UX, freshness, licensing compliance, or operational monitoring. Such checks remain unassessed until dedicated validators exist.
- The manifest is a deterministic package description, not a customer-facing application/report/map and not a publication record.
- Release/deployment/operation remain separate services and approval boundaries.

## Consequences

Foundry can distinguish successful execution, accepted product, and release eligibility. The manifest gives downstream packaging/publishing services a stable provenance and artifact inventory without prematurely conflating acceptance with deployment.
