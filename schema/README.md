# Foundry schema contracts

The JSON files in this directory are the canonical structural contracts. They use JSON Schema Draft 2020-12 and stable versioned URN identifiers.

## Contracts

| File | Describes |
|---|---|
| _common.schema.json | Shared identifiers, references, CRS, extents, timestamps and checksum definitions |
| artifact.schema.json | One immutable version of a logical data Artifact |
| capability.schema.json | One version of an engine-independent Capability contract |
| capability-implementation.schema.json | One versioned engine/runtime realization of a Capability |
| cell.schema.json | One immutable Geo-Cell computation declaration |
| recipe.schema.json | One immutable DAG of exact Geo-Cell versions |
| run.schema.json | One execution attempt and its provenance |
| validation-report.schema.json | Evidence for validating a specific subject and stage |

## Versioning

Schema identifiers use the namespace:

    urn:tessellatum-foundry:schema:<name>:<version>

The initial schema version is 1.0.0. Shared definitions are referenced by absolute URN so consumers can register schemas locally without network access or dependence on repository paths.

Breaking changes to a schema's accepted structure or meaning require a new schema version and a documented compatibility decision.

## Validation boundary

JSON Schema checks structure and local constraints. It does not establish that referenced records exist, graph edges are consistent, CRS and units are compatible, a method is appropriate, or a runtime output is correct. Those checks belong to semantic and execution validators.

Run:

    python scripts/validate_schemas.py

or:

    python -m pytest

from the repository root after installing the development dependencies.
