# ADR-046: Bulk geospatial object storage boundary (superseded)

- **Status:** Superseded by [ADR-047](047-external-data-computation-boundary.md)
- **Date:** 2026-11-22

This proposal separated bulk geospatial source bytes from a PostGIS information index and described object-storage-backed source snapshots and streaming ingestion.

Although the separation is technically sound for a data warehouse, making Foundry responsible for source snapshots still creates a source-data custody and retention platform that is not required by Foundry's computational purpose. The source snapshot uploader and related information schema are therefore removed from active Foundry code.

Foundry may use customer-selected or future artifact storage for derived computational outputs. It does not mandate copying source datasets. See ADR-047.
