# Foundry Console

The Console is a static, same-origin browser interface for the private control-plane API. It supports connecting with a bearer token, inspecting registries, uploading Artifacts with JSON metadata, registering Cell and Recipe documents, executing Recipes, inspecting Runs and Validation Reports, and downloading output Artifacts with SHA-256 verification.

## Build

From the repository root:

```bash
docker build -f deploy/console/Dockerfile \
  -t tessellatum-foundry/console:0.1.0 .
```

The image uses an unprivileged Nginx runtime and contains only the static HTML, CSS, and JavaScript console. No third-party browser libraries, analytics, external fonts, or remote scripts are loaded.

## Run beside the control plane

The console container must share a private Docker network with the control plane container named `foundry-control-plane`. The Nginx configuration proxies the same-origin `/api/` path to that container and strips the prefix before forwarding.

```bash
docker run -d \
  --name foundry-console \
  --restart unless-stopped \
  --network foundry-private \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 64 \
  --memory 128m \
  --cpus 0.5 \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m \
  -p 127.0.0.1:8081:8080 \
  tessellatum-foundry/console:0.1.0
```

Place a trusted TLS ingress in front of the loopback binding and route the public/private hostname to port 8081. The control plane must also be attached to `foundry-private`. Do not expose port 8081 or the control-plane port directly to the public internet.

## Security model

- The browser accepts only a same-origin API path (default `/api`); external API URLs are rejected to avoid sending the token to arbitrary origins.
- The bearer token is held in JavaScript memory only, the password input is cleared after connection, and disconnect/reload clears the in-memory token. The console does not use localStorage, sessionStorage, cookies, or URL parameters for credentials.
- Fetch requests reject redirects and use same-origin credentials. The API itself still enforces the bearer token on all `/v1` routes.
- The Nginx response policy sets a restrictive Content Security Policy, nosniff, no-referrer, and frame-denial headers. The console has no inline script or style.
- Output Artifact downloads verify byte length and SHA-256 against both the Artifact metadata and response header before prompting the browser to save the file.

This is an operator console for a single-tenant private preview, not an identity provider. Anyone with the shared API token has the same permissions. Serve it only behind TLS and trusted access controls; rotate the token if it may have been exposed.

## Current limits

The Console is an operational surface, not a full visual workflow designer. It accepts canonical Cell/Recipe JSON rather than providing a graphical DAG editor, map viewer, geospatial preview, multi-user permissions, or per-tenant workspaces. It limits file uploads to 20 MiB. The underlying control plane and remote workers retain the limitations described in [the control-plane deployment guide](../control-plane/README.md).
