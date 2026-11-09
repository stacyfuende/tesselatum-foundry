# Quickstart: first spatial Run

This example is intentionally small and deterministic. It uses synthetic polygon features in EPSG:32737, buffers them by 10 metres, and records the output Artifact, Run, and Validation Reports in a local workspace.

## Prerequisites

- Python 3.11+
- Docker Engine running
- A source checkout of this repository

## 1. Install Foundry and build the isolated worker

From the repository root:

```bash
python -m pip install -e '.[dev,shapely]'
docker build \
  -f workers/vector_buffer/Dockerfile \
  -t tessellatum-foundry/vector-buffer-shapely:ci \
  .
```

The CLI does not build or pull worker images automatically. The worker runs without network access, with a read-only root filesystem, non-root identity, dropped Linux capabilities, and configured CPU/memory/process limits.

## 2. Initialize and ingest the synthetic input

```bash
foundry --data-dir ./foundry-data init

foundry --data-dir ./foundry-data artifact put \
  --id quickstart.sites --version 1.0.0 \
  --file examples/quickstart/sites.geojson \
  --created-by quickstart \
  --media-type application/vnd.tessellatum.spatial-feature-collection+json \
  --format 'Foundry Spatial Feature Collection JSON' \
  --spatial-json examples/quickstart/sites.spatial.json \
  --metadata-json examples/quickstart/sites.metadata.json
```

The input contains two synthetic square polygons. Their CRS and extent are supplied separately as canonical Artifact metadata.

## 3. Register and validate the computation

```bash
foundry --data-dir ./foundry-data validate \
  --schema cell.schema.json \
  --file examples/quickstart/buffer.cell.json

foundry --data-dir ./foundry-data cell register \
  --file examples/quickstart/buffer.cell.json \
  --created-by quickstart

foundry --data-dir ./foundry-data recipe register \
  --file examples/quickstart/buffer.recipe.json \
  --created-by quickstart
```

## 4. Execute the Recipe

```bash
foundry --data-dir ./foundry-data recipe run \
  --id quickstart-site-buffers --version 1.0.0 \
  --actor-id quickstart
```

A successful response includes the Recipe execution ID, per-node Run IDs, and declared output Artifact metadata. A failed execution returns a non-zero status and identifies the failed node.

## 5. Inspect and export the result

```bash
foundry --data-dir ./foundry-data runs

foundry --data-dir ./foundry-data artifact export \
  --id OUTPUT_ARTIFACT_ID --version OUTPUT_VERSION \
  --output ./buffered-sites.geojson
```

Replace the output ID and version with the Artifact reference returned by the Recipe execution. Export verifies the Artifact checksum before writing the bytes.

## What this demonstrates—and what it does not

This quickstart demonstrates one local vector.buffer Run through the canonical Capability, immutable Artifact and definition stores, isolated Docker worker, independent output critic, and Recipe runner. It is a smoke path, not full CI or a production deployment.

The sample data are synthetic. No real site suitability, legal rights, positional accuracy, or planning conclusion is implied. The local CLI is single-user; do not expose it, its workspace, or the Docker socket to untrusted users. Hosted multi-tenant deployment remains a separate launch milestone.
