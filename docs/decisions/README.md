# Architecture Decision Register

This register records decisions that constrain Foundry's architecture. Each decision includes its status, context, decision, consequences, and alternatives.

| ID | Decision | Status |
|---|---|---|
| [001](001-five-concept-domain-model.md) | Separate the five domain concepts | Accepted |
| [002](002-geo-cell-is-computation-declaration.md) | Geo-Cell is computation declaration only | Accepted |
| [003](003-contract-first-api-and-viewer.md) | Canonical contracts/API; read-only viewer in v0.1 | Accepted |
| [004](004-control-compute-plane-and-workers.md) | Separate control/compute planes; local and remote workers | Accepted |
| [005](005-capability-contract-and-conformance.md) | Capability contract separate from implementations | Accepted |
| [006](006-optional-planner-boundary.md) | Planner is optional and outside execution core | Accepted |
| [007](007-json-schema-and-semantic-validation.md) | JSON Schema plus semantic validation | Accepted |

A decision may be superseded only by a new decision record that explains the change. Do not silently edit an accepted decision to reverse its meaning.
