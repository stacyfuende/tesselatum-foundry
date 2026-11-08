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
| [008](008-cell-bindings-and-recipe-edges.md) | Explicit cell bindings mirrored by Recipe edges | Accepted |
| [009](009-versioned-schema-identifiers.md) | Stable versioned schema identifiers | Accepted |
| [010](010-validation-report-subject-identity.md) | Validation reports identify runs by run ID, not version | Accepted |
| [011](011-python-toolchain-and-package-layout.md) | Python 3.11+ src-layout and validation toolchain | Accepted |
| [012](012-unique-cell-version-per-recipe.md) | Each Recipe contains a cell version at most once | Accepted |
| [013](013-single-binding-per-input-port-v0.1.md) | One binding per named input port in v0.1 | Accepted |
| [014](014-retries-create-new-run-attempts.md) | Retry creates a new Run; prior attempt stays terminal | Accepted |
| [015](015-spatial-metadata-validation.md) | Spatial metadata and pre-execution CRS/unit validation | Accepted |
| [016](016-first-executable-capability-vector-buffer.md) | First executable capability and explicit planar buffer semantics | Accepted |
| [017](017-shared-buffer-validation-and-postgis-conformance.md) | Shared request validation and independent PostGIS conformance | Accepted |

A decision may be superseded only by a new decision record that explains the change. Do not silently edit an accepted decision to reverse its meaning.
