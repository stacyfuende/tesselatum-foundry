# ADR-064: Customer request to verified product delivery

- **Status:** Proposed
- **Date:** 2026-11-28
- **Decision area:** Product Factory / customer execution lifecycle

## Decision

Introduce one orchestration boundary that composes existing registered services in this order:

1. Resolve customer intent against an installed, approved product template.
2. Validate and persist source bytes as an immutable Artifact.
3. Bind the exact Artifact identity to the approved product input.
4. Compile using caller-supplied, reviewed Cell templates and explicit output mappings.
5. Re-plan against current capability and autonomy policy, then execute through the existing Recipe Run service.
6. Evaluate registered acceptance validators.
7. Assemble the provenance-rich product manifest.
8. Export a bounded ZIP only when acceptance explicitly allows release.

The service returns the verified ZIP bytes and a customer-facing status/summary. It does not synthesize execution capabilities or Cell templates from customer text.

## Security and product boundary

- Existing planning, autonomy, immutable definition, Recipe Run, Artifact checksum and acceptance gates remain authoritative.
- A failed or unaccepted execution cannot produce a delivery bundle.
- Source and export byte limits remain configurable and bounded.
- The orchestration function is an application service, not a public HTTP endpoint. Authentication, tenant isolation, upload streaming, rate limiting, malware scanning, storage lifecycle and hosted delivery remain deployment concerns.

## Consequences

The complete transaction can now be invoked as one application operation and tested without exposing internal Blueprint, Artifact or Recipe vocabulary to customers. A deployment adapter can expose it through an authenticated endpoint without duplicating the lifecycle.
