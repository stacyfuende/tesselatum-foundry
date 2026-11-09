# Local operator CLI

The `foundry` command is the operator interface for a persistent, single-user local Foundry workspace. It exposes the existing contracts, immutable stores, sequential Recipe runner, Run history, and Validation Reports without introducing a second workflow format.

## Install

From a source checkout:

```bash
python -m pip install -e '.[dev,shapely]'
```

The CLI entry point is installed as `foundry`. Recipe execution uses the existing isolated Docker workers, so Docker Engine must be available and the matching worker images must already be built or pulled. The CLI does not silently build or pull images.

## Initialize a workspace

```bash
foundry --data-dir ./foundry-data init
```

The workspace persists Artifact bytes, immutable Cell/Recipe definitions, Runs, and Validation Reports beneath the selected directory. Back up this directory as a unit. It is a local filesystem workspace, not a multi-user database or a network service.

## Register definitions

```bash
foundry --data-dir ./foundry-data cell register \
  --file ./definitions/site-buffer.cell.json \
  --created-by operator

foundry --data-dir ./foundry-data recipe register \
  --file ./definitions/site-selection.recipe.json \
  --created-by operator
```

Definitions are immutable by ID and version. Registering a new version is the way to change a definition. Registration checks the canonical JSON Schema and immutable identity; Recipe graph, reference, spatial, implementation-conformance, and worker preconditions are checked before execution.

## Ingest an Artifact

```bash
foundry --data-dir ./foundry-data artifact put \
  --id sites --version 1.0.0 \
  --file ./data/sites.geojson \
  --created-by operator \
  --media-type application/vnd.tessellatum.spatial-feature-collection+json \
  --format 'Foundry Spatial Feature Collection JSON' \
  --spatial-json ./metadata/sites.spatial.json \
  --rights-json ./metadata/sites.rights.json
```

The file bytes are stored immutably and identified by SHA-256. Spatial, rights, and general metadata are optional JSON object files. The caller is responsible for supplying metadata that accurately describes the source data; recording a rights declaration does not establish legal permission.

## Execute and inspect

```bash
foundry --data-dir ./foundry-data recipe run \
  --id site-selection --version 1.0.0 --actor-id operator

foundry --data-dir ./foundry-data runs
foundry --data-dir ./foundry-data run show RUN_ID
foundry --data-dir ./foundry-data report show REPORT_ID
foundry --data-dir ./foundry-data artifact show --id sites --version 1.0.0
```

A failed Recipe returns a non-zero exit status and a JSON summary identifying the failed node and completed Runs. Earlier successful Runs remain recorded; a retry is a new execution, not a rewrite of history.

## Export an Artifact

```bash
foundry --data-dir ./foundry-data artifact export \
  --id sites --version 1.0.0 --output ./exports/sites.geojson
```

Export reads the stored object through the Artifact store and verifies its SHA-256 checksum and byte length before writing the destination file.

## Inspect the registries

```bash
foundry --data-dir ./foundry-data capabilities
foundry --data-dir ./foundry-data implementations
```

Only implementations whose canonical manifest records passed conformance are eligible for execution. A listed implementation is not necessarily configured with a locally available Docker image.

## Launch boundary

This CLI is a useful local operator workflow, not a production hosted service. The filesystem repositories use process-local concurrency control and are not safe as a shared multi-process database. There is no tenant isolation, user authentication, API server, browser authoring interface, managed object storage, or production deployment profile yet. Do not expose the workspace directory or local Docker socket to untrusted users.

Before a hosted launch, deploy a separate authenticated control plane with tenant-scoped persistence and authorization, managed Artifact storage, worker isolation and resource quotas, secret management, backups, observability, and operational recovery procedures. Run the acceptance suite and record exact runtime/conformance evidence before changing any implementation manifest from `not_run`.
