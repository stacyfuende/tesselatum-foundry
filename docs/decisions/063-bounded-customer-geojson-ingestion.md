# ADR-063: Bounded customer GeoJSON source ingestion

- **Status:** Proposed
- **Date:** 2026-11-28
- **Decision area:** Product Factory / source ingestion

## Context

The customer request composer can describe a supported site-coordinate job and inspect a file locally, but it cannot yet make that file available to the guarded execution service. A request must not be considered executable until its actual source bytes have been validated and registered as an immutable Artifact.

## Decision

Add a bounded ingestion service for the Nairobi site-coordinate product:

- Resolve the customer request against the installed product template before accepting bytes.
- Enforce a 25 MiB default byte limit and a 100,000-feature default limit.
- Parse UTF-8 GeoJSON as a non-empty FeatureCollection of Point features, with 2D or 3D finite WGS 84 longitude/latitude coordinates.
- Reject legacy embedded CRS declarations; the customer request must explicitly declare EPSG:4326.
- Enforce the same pilot geographic envelope as the customer intake page.
- Preserve original source bytes, feature IDs, properties and coordinate values.
- Register a content-addressed immutable Artifact with vector metadata, EPSG:4326, geometry type, observed bounds, feature count and request provenance.
- Return an exact Artifact input binding for the registered vector.reproject capability.

## Boundary

Ingestion does not execute a Run, transform coordinates, certify survey accuracy, validate legal boundaries, or publish a product. The returned binding must still pass through the existing Blueprint compilation, autonomy checks and Recipe Run service.

The filesystem store is the current development adapter. This ADR does not claim production multi-tenant upload, object-store isolation, authentication, malware scanning, retention policy or hosted API availability.

## Consequences

A customer source can now cross the boundary from local request description to a verified immutable input Artifact. The next step is to connect this operation to an authenticated upload endpoint and then invoke the existing guarded product execution lifecycle.
