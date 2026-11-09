# ADR-045: Declare normative capability semantics in the canonical schema

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

ADR-044 introduced `raster.band_statistics@1.0.0` with a `semantics` array. The canonical `capability.schema.json` uses `additionalProperties: false` but did not declare that field. As a result, the installed-distribution smoke test rejects the new raster Capability before linting, conformance, Docker builds, or the test suite can run.

The semantics statements are normative: they define how consumers must interpret the operation's results. They are not implementation-specific metadata and should remain part of the engine-independent Capability contract.

## Decision

1. Add an optional top-level `semantics` property to the canonical Capability JSON Schema.
2. Define it as an array of non-empty strings with unique items.
3. Keep it optional so existing Capability contracts remain valid without modification.
4. Add a regression test that loads the actual checked-in raster Capability JSON and validates it against the canonical schema.
5. Test rejection of empty and duplicate semantics entries.
6. Do not weaken `additionalProperties: false` or remove the raster contract's normative statements.

## Consequences

- The raster Capability can express its normative value semantics without violating the canonical schema.
- Existing contracts remain backwards-compatible because the property is optional.
- Future capability authors can use the same field for concise, engine-independent interpretation requirements.
- The schema regression test catches drift between checked-in capability definitions and the canonical contract schema.

## Verification status

The schema and test changes are committed to the isolated working branch `fix/raster-capability-semantics-schema`. GitHub Actions were not triggered by these branch updates. Local test execution has not yet been performed; CI verification remains pending and the raster implementation manifest must remain `not_run`.
