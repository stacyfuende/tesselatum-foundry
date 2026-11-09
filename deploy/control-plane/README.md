# Private single-tenant control plane

The control-plane image exposes the authenticated Foundry HTTP API. It is an initial private deployment target, not a public multi-tenant SaaS service.

## Run API tests without invoking GitHub Actions

From the repository root:

```bash
python -m pip install -e '.[dev,shapely]'
python -m pytest tests/test_api.py
```

The development extra includes FastAPI and its test client. These tests use an injected temporary local workspace and do not start Docker workers or contact external services.

## Build

From the repository root:

```bash
docker build -f deploy/control-plane/Dockerfile \
  -t tessellatum-foundry/control-plane:0.1.0 .
```

The image runs as UID/GID 10001, uses one Uvicorn worker to preserve the filesystem repository's process-local concurrency model, disables interactive API documentation, and does not contain or mount the Docker socket.

## Configure secrets and remote workers

Build the shared remote-worker image once:

```bash
docker build -f workers/vector_buffer/Dockerfile.remote \
  -t tessellatum-foundry/remote-vector-worker:0.1.0 .
docker image inspect --format='{{.Id}}' \
  tessellatum-foundry/remote-vector-worker:0.1.0
```

Use the returned immutable `sha256:...` image ID as `FOUNDRY_WORKER_IMAGE_DIGEST` for the worker containers. Run two separate worker processes from this image, each on a private network and behind its own trusted TLS ingress:

- Buffer: `FOUNDRY_WORKER_CAPABILITY_ID=vector.buffer`, `FOUNDRY_WORKER_CAPABILITY_VERSION=1.0.0`, and a unique `FOUNDRY_REMOTE_WORKER_TOKEN`.
- Reprojection: `FOUNDRY_WORKER_CAPABILITY_ID=vector.reproject`, `FOUNDRY_WORKER_CAPABILITY_VERSION=1.0.0`, `FOUNDRY_IMPLEMENTATION_ID=vector-reproject-pyproj-shapely`, and a different unique `FOUNDRY_REMOTE_WORKER_TOKEN`.

Copy `deploy/remote-worker.env.example` separately for each worker and populate unique tokens, worker IDs, and the immutable image ID. For reprojection, change the capability ID to `vector.reproject` and implementation ID to `vector-reproject-pyproj-shapely`. Keep the worker execution deadline at 110 seconds unless you also raise the control-plane adapter timeout, Python client execution timeout, and reverse-proxy timeout. The example defaults are 110 seconds in the worker, 120 seconds in the API adapter, 145 seconds in the Python client, and 150 seconds in Nginx.

Each process advertises and executes exactly one capability. The default process semaphore allows two active executions; overload returns HTTP 503 with `Retry-After`, while a hard child-process deadline returns HTTP 504 and becomes a timed-out Run. Do not expose the worker's plain HTTP port publicly; allow inbound traffic only from the control plane through the TLS ingress.

The worker distinguishes `FOUNDRY_MAX_INPUT_BYTES` (the compact serialized FeatureCollection ceiling) from `FOUNDRY_MAX_REQUEST_BYTES` (the complete HTTP JSON request ceiling). The request ceiling defaults to the input ceiling plus 1 MiB. Keep the API adapter's `FOUNDRY_REMOTE_WORKER_MAX_INPUT_BYTES` aligned with the worker's input ceiling; the checked-in environment examples use 64 MiB for both.


Copy `deploy/control-plane/env.example` to a secret-managed location outside the repository. Set:
- `FOUNDRY_API_TOKEN` to a random value of at least 32 characters.
- Separate strong bearer tokens for the buffer and reprojection workers.
- HTTPS base URLs for the corresponding worker services.
- Request and response byte ceilings appropriate for the Artifact sizes you will accept and return.
- The control-plane-to-worker timeout and worker input/output ceilings. The checked-in examples align the raw/serialized FeatureCollection input ceiling at 64 MiB and output ceiling at 128 MiB. The worker HTTP request ceiling is 65 MiB to allow up to 1 MiB for the JSON envelope around the input; this is distinct from the FeatureCollection input ceiling. The adapter timeout example is 120 seconds and the remote worker child-process deadline is 110 seconds.

For example, generate an API token with `openssl rand -hex 32`. Never commit populated environment files or put tokens in image build arguments.

Build one remote worker image for each capability deployment. Each worker process advertises exactly one capability version. Configure the worker's `FOUNDRY_WORKER_CAPABILITY_ID`, `FOUNDRY_WORKER_CAPABILITY_VERSION`, `FOUNDRY_IMPLEMENTATION_ID`, `FOUNDRY_REMOTE_WORKER_TOKEN`, and `FOUNDRY_WORKER_IMAGE_DIGEST`. The digest must be the immutable image ID reported by Docker for the image actually running. The remote worker requires TLS at a trusted ingress; its plain HTTP listener must remain on a private network.

## Run the two worker processes

Use the separate env files for the buffer and reprojection workers. The same image is configured to advertise one capability per process. Publish each worker only on a loopback host port so a TLS ingress can reach it; do not publish the worker port on a public interface.

```bash
docker run -d \
  --name foundry-buffer-worker \
  --restart unless-stopped \
  --network foundry-private \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 2g \
  --cpus 2.0 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --env-file /secure/path/foundry-buffer-worker.env \
  -p 127.0.0.1:8081:8080 \
  tessellatum-foundry/remote-vector-worker:0.1.0

docker run -d \
  --name foundry-reproject-worker \
  --restart unless-stopped \
  --network foundry-private \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 2g \
  --cpus 2.0 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --env-file /secure/path/foundry-reproject-worker.env \
  -p 127.0.0.1:8082:8080 \
  tessellatum-foundry/remote-vector-worker:0.1.0
```

The ingress for each loopback port must terminate TLS and enforce an allowlist so only the control plane can call the worker. Apply network egress restrictions to the worker containers; do not assume process isolation alone prevents outbound network access. The worker child processes share the worker container's network namespace and resource ceiling.

## Run behind a trusted ingress

Create a persistent Docker volume and run the API container on a private network. A minimal local binding is:

```bash
docker network create foundry-private
docker volume create foundry-control-data
docker run -d \
  --name foundry-control-plane \
  --restart unless-stopped \
  --network foundry-private \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 1g \
  --cpus 1.0 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount source=foundry-control-data,target=/var/lib/foundry \
  --env-file /secure/path/foundry-control-plane.env \
  -p 127.0.0.1:8000:8000 \
  tessellatum-foundry/control-plane:0.1.0
```

Place a TLS-terminating reverse proxy in front of the loopback binding. Apply ingress authentication/rate limits, request-body limits, connection limits, and network rules that permit the API to reach only its designated workers and required infrastructure. Do not expose worker ports to the public internet. Back up the persistent volume and test restoration before storing valuable data.

## API surface

All `/v1` routes require `Authorization: Bearer <FOUNDRY_API_TOKEN>`. The health endpoint is intentionally unauthenticated and returns no operational details.

- `GET /v1/capabilities`, `GET /v1/implementations`
- `POST /v1/artifacts` (base64 content plus metadata); `GET /v1/artifacts/{id}/{version}`; `GET /v1/artifacts/{id}/{version}/content`
- `POST /v1/cells`, `GET /v1/cells`, `GET /v1/cells/{id}/{version}`
- `POST /v1/recipes`, `GET /v1/recipes`, `GET /v1/recipes/{id}/{version}`
- `POST /v1/recipes/{id}/{version}/runs`
- `GET /v1/runs`, `GET /v1/runs/{run_id}`, `GET /v1/reports/{report_id}`

The API rejects missing or invalid bearer tokens, non-JSON bodies, missing Content-Length, oversized requests, malformed base64, and unknown fields on write operations. Artifact responses replace local filesystem paths with an opaque `foundry://sha256/...` storage identifier; retrieve bytes through the authenticated content endpoint. Responses disable caching and set basic content-sniffing/referrer protections. Interactive OpenAPI/Swagger documentation is disabled.

## Python API client

The repository includes a dependency-free synchronous `FoundryClient` for this API:

```python
import json
import os
from pathlib import Path

from tessellatum_foundry import FoundryClient

example = Path("examples/quickstart")
client = FoundryClient(
    "https://foundry.example.internal",
    bearer_token=os.environ["FOUNDRY_API_TOKEN"],
)

artifact = client.put_artifact(
    artifact_id="quickstart.sites",
    version="1.0.0",
    content=(example / "sites.geojson").read_bytes(),
    created_by="operator",
    media_type="application/vnd.tessellatum.spatial-feature-collection+json",
    format_name="Foundry Spatial Feature Collection JSON",
    spatial=json.loads((example / "sites.spatial.json").read_text()),
)
cell_definition = json.loads((example / "buffer.cell.json").read_text())
recipe_definition = json.loads((example / "buffer.recipe.json").read_text())
client.register_cell(cell_definition, created_by="operator")
recipe = client.register_recipe(recipe_definition, created_by="operator")
result = client.execute_recipe(
    recipe["definition_ref"]["definition_id"],
    recipe["definition_ref"]["version"],
    actor_id="operator",
)
output = result["outputs"]["buffered_sites"]
verified_bytes = client.read_artifact(output["artifact_id"], output["version"])
```

The client enforces HTTPS by default, rejects redirects, bounds request/response sizes (32 MiB request / 128 MiB response by default), and verifies downloaded Artifact bytes against both the immutable metadata checksum and the response digest header. Normal calls default to a 30-second timeout; Recipe execution defaults to 145 seconds to exceed the worker's 110-second deadline while remaining below the example Nginx 150-second upstream timeout. If you change the worker deadline, align the API adapter, client execution timeout, API response ceiling, and reverse-proxy timeout together. For local HTTP-only tests, callers must explicitly enable `allow_insecure_localhost=True`. API and client tests run with `python -m pip install -e '.[dev,shapely]'` followed by `python -m pytest tests/test_api.py tests/test_client.py`.

## Important launch limitations

This deployment is **single-tenant**: every authorized caller shares one API token and one workspace. It has no user identities, roles, tenant isolation, quotas, database-backed distributed transactions, object-storage adapter, or per-tenant encryption. The filesystem stores remain local to one control-plane process; do not increase Uvicorn workers or run multiple replicas against the same volume.

The concurrency-bound and process-isolated hard-timeout implementations from PRs #13 and #15 have now been ported onto the isolated build branch, but have not yet been executed or reviewed in the complete integration context. Do not consider remote workers production-hardened until the complete tests pass and container-level overload/timeout drills are recorded. A reverse proxy must provide TLS, network restrictions, rate limiting, and ingress resource limits. Secret rotation requires coordinated worker/API configuration updates and restarts.

The API is an integration foundation for a controlled private preview. It is not permission to expose the service publicly. Complete the remaining acceptance tests, worker hardening, backup/restore exercise, security review, and operational monitoring before a production launch.
