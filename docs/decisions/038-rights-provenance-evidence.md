# ADR-038: Record rights provenance without inferring permission

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Artifacts may carry optional rights metadata. Vector execution already copies the input rights object to its output, and cache validation compares the candidate output rights with the current input rights. However, an absent rights object and a recorded licence identifier are not evidence that a proposed use is legally permitted. The execution output critic explicitly leaves rights/security policy unassessed.

Foundry needs to preserve the declaration and its lineage while avoiding an accidental legal conclusion. Execution, licence interpretation, and authorization for publication or redistribution are distinct questions.

## Decision

1. Preserve the exact input Artifact rights object on derived vector Artifacts. Never synthesize a licence, attribution, permitted-use list, or restriction.
2. Record the exact source Artifact identity in output metadata under `rights_provenance.source_artifact`, together with a declaration state of `unknown` or `declared_unverified`.
3. Persist a separate `rights_security` Validation Report for every successful vector Run, including cache-hit Runs.
4. The rights provenance critic may establish whether a rights object and licence identifier are recorded. It must not interpret licence terms or assert that the operation, intended purpose, publication, or redistribution is permitted.
5. Missing or incomplete declarations produce `requires_review`; a recorded licence identifier produces `not_assessed`, not `passed`. Permission remains explicitly unassessed until an authoritative policy evaluator exists.
6. Rights reports are linked from the immutable Run through `validation_report_ids`. They supplement, and do not replace, execution/output validation.
7. Cache reuse continues to require exact rights metadata equality and checksum-verified output provenance. Cache reuse does not confer publication or redistribution permission.

## Consequences

- Unknown rights remain visible and cannot be mistaken for a permissive default.
- Derived Artifacts retain both the declaration and an explicit pointer to the immediate source Artifact.
- Rights evidence is queryable alongside execution evidence without blocking computational execution solely because legal interpretation is not implemented.
- A future policy engine can evaluate intended use against authoritative licence terms without rewriting historical declarations or reports.

## Alternatives considered

- **Treat missing rights as unrestricted:** rejected; absence is not permission.
- **Block all execution when rights are unknown:** deferred; computation and legal authorization are distinct, and this release records the uncertainty without asserting permission.
- **Treat any licence identifier as authorization:** rejected; a label alone does not establish applicability, compliance, or downstream redistribution rights.
