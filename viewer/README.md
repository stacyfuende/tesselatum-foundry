# Read-only Recipe DAG viewer

The viewer is a dependency-free static HTML page. Open `viewer/index.html` in a browser, then paste a canonical Recipe JSON document or select the JSON file from disk. For a sample, load `tests/fixtures/valid/recipe.valid.json` from the repository root.

It displays:
- Recipe ID, version, and title;
- Geo-Cell nodes with exact Cell IDs and versions;
- directed output-to-input dependencies, arranged by topological depth; and
- declared Recipe outputs.

The viewer is deliberately read-only. It does not edit the Recipe, create a second workflow representation, execute cells, resolve Artifact references, or replace the canonical JSON Schema and semantic graph validators. A cycle or structurally unusable edge is reported rather than rendered as a valid DAG.

No frontend build, package installation, network service, or external JavaScript dependency is required.
