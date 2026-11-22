# ADR-045: Persistent spatial information core (superseded)

- **Status:** Superseded by [ADR-047](047-external-data-computation-boundary.md)
- **Date:** 2026-11-22

This proposal explored making Foundry the canonical owner of geographic entity identity, source records, observations, representations and relationships in PostgreSQL/PostGIS.

After reassessing Foundry's trajectory, this is not the platform responsibility. Foundry should make externally held spatial data computable and own computation contracts, execution, validation and provenance. The proposed schema, repository adapter and ingestion direction are not part of the active implementation.

The original proposal is retained in Git history for context. See ADR-047 for the accepted decision.
