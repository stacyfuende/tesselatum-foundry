# ADR-065: Authenticated customer product submission API

- **Status:** Proposed
- **Date:** 2026-11-28

## Decision

Provide a narrow HTTP adapter at `POST /v1/products`. It accepts a versioned JSON envelope containing the customer-language request and base64-encoded GeoJSON source. The adapter authenticates before reading or resolving tenant runtime services, enforces request/source byte limits, delegates the complete transaction to `run_customer_spatial_product`, and returns the accepted ZIP as an attachment.

Authentication and tenant runtime resolution are injected by the hosting application. The request body cannot select an actor, tenant, storage backend, capability, Cell template or output mapping.

## Security boundary

- The runtime resolver must return tenant-isolated Artifact stores and execution services.
- The host must provide strong authentication, TLS, ingress rate limits, concurrency limits, request timeouts and secret rotation.
- No CORS policy or browser bearer-token storage is provided. The static request composer remains local-only until a session-authenticated frontend is integrated.
- The standard-library server is an adapter suitable for private deployment behind a trusted ingress, not a complete public multi-tenant hosting platform.
- Source data is decoded in memory within explicit limits; large uploads require a streaming transport rather than base64 JSON.

## Consequences

The customer workflow now has a stable authenticated HTTP contract without coupling product logic to a web framework or trusting customer-supplied execution configuration. Hosting still must supply identity and tenant isolation correctly before public exposure.
