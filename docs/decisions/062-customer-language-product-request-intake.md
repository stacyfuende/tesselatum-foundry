# ADR-062: Customer-language product request intake

- **Status:** Proposed
- **Date:** 2026-11-28
- **Decision area:** Product Factory / customer entry

## Context

A customer should describe the spatial job and provide the source data without authoring a Blueprint, selecting capabilities, or assembling a Recipe. The execution core must nevertheless remain deterministic and restricted to registered, reviewed methods.

## Decision

Introduce a separate `customer_product_request.schema.json` contract and a deterministic request resolver. The first supported request is Nairobi site-coordinate standardization:

- The customer supplies a GeoJSON file declared as EPSG:4326 (longitude, latitude).
- The supported geographic scope is restricted to the Nairobi metropolitan region because the approved output CRS is EPSG:32737.
- The customer supplies audience and decision context; the resolver carries these into the approved Product Blueprint.
- The resolver plans only the exact installed Blueprint template and registered capabilities. It does not generate code, methods, or new execution graphs.
- The resolver returns a customer-readable summary and a separate internal execution plan.

## Boundary

This is an intake-to-plan step, not a file upload or execution service. The request resolver does not read customer file bytes, create an Artifact, assert geometry validity, or start a Run. The request remains `awaiting_source_ingestion` until a separate ingestion step validates and stores the source as an immutable Artifact. The existing guarded product execution handoff remains responsible for binding that Artifact and executing.

Unsupported geography, file types, CRS declarations, template substitutions, or unregistered jobs fail closed.

## Consequences

- Customers can express one useful spatial job without understanding Foundry internals.
- Product scope is explicit and deliberately narrow; this is not a universal natural-language-to-spatial-code interface.
- The next engineering step is a bounded GeoJSON intake path that validates file bytes, feature structure, coordinate ranges and the declared Nairobi operating area before immutable Artifact registration.
