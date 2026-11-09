# Private single-tenant control plane

The control-plane image exposes the authenticated Foundry HTTP API. It is an initial private deployment target, not a public multi-tenant SaaS service.

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

Each process advertises and executes exactly one capability. Do not expose the worker's plain HTTP port publicly; allow inbound traffic only from the control plane through the TLS ingress.


Copy `deploy/control-plane/env.example` to a secret-managed location outside the repository. Set:
- `FOUNDRY_API_TOKEN` to a random value of at least 32 characters.
- Separate strong bearer tokens for the buffer and reprojection workers.
- HTTPS base URLs for the corresponding worker services.
- A request-size limit appropriate for the data being uploaded.

For example, generate an API token with `openssl rand -hex 32`. Never commit populated environment files or put tokens in image build arguments.

Build one remote worker image for each capability deployment. Each worker process advertises exactly one capability version. Configure the worker's `FOUNDRY_WORKER_CAPABILITY_ID`, `FOUNDRY_WORKER_CAPABILITY_VERSION`, `FOUNDRY_IMPLEMENTATION_ID`, `FOUNDRY_REMOTE_WORKER_TOKEN`, and `FOUNDRY_WORKER_IMAGE_DIGEST`. The digest must be the immutable image ID reported by Docker for the image actually running. The remote worker requires TLS at a trusted ingress; its plain HTTP listener must remain on a private network.

## Run behind a trusted ingress

Create a persistent Docker volume and run the API container on a private network. A minimal local binding is:

```bash
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

## Important launch limitations

This deployment is **single-tenant**: every authorized caller shares one API token and one workspace. It has no user identities, roles, tenant isolation, quotas, database-backed distributed transactions, object-storage adapter, or per-tenant encryption. The filesystem stores remain local to one control-plane process; do not increase Uvicorn workers or run multiple replicas against the same volume.

The remote worker concurrency-bound and hard-timeout work is still under review in PRs #13 and #15. The current remote worker server must not be considered production-hardened until those changes are reviewed, integrated, and tested in containers. A reverse proxy must provide TLS, network restrictions, rate limiting, and ingress resource limits. Secret rotation requires coordinated worker/API configuration updates and restarts.

The API is an integration foundation for a controlled private preview. It is not permission to expose the service publicly. Complete the remaining acceptance tests, worker hardening, backup/restore exercise, security review, and operational monitoring before a production launch.
