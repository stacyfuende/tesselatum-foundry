# ADR-040: Enforce remote capability execution deadlines in isolated child processes

- **Status:** Accepted
- **Date:** 2026-11-09
- **Supersedes:** The per-execution wall-clock limitation recorded in ADR-039.

## Context

The remote HTTP worker previously executed Shapely/PyProj capability functions inside the request-handler thread. The control-plane HTTP timeout only bounds how long the client waits; it does not stop a computation already running in the remote server process. A hung or unusually expensive geometry operation could therefore hold a concurrency slot indefinitely.

The repository already has a worker CLI that executes the exact capability request contract in a separate process and applies an output file-size limit.

## Decision

1. Execute each remote capability request through `python -m tessellatum_foundry.worker.cli` in a child process rather than invoking capability functions inside the HTTP handler.
2. Write the normalized worker request, input FeatureCollection and output to a private temporary directory. Do not pass bearer credentials or HTTP headers to the child process.
3. Enforce a hard wall-clock timeout with `subprocess.run(timeout=...)`. The default is 110 seconds; configure `FOUNDRY_EXECUTION_TIMEOUT_SECONDS` from 1 through 3600.
4. On timeout, terminate the child process and return HTTP 504 with a stable `worker_execution_timeout` error code.
5. On non-zero exit, missing output, invalid output JSON or output-size violation, fail the request. Never return partial output as a successful execution.
6. Preserve the CLI's output file-size limit and the HTTP server's response-size limit. Continue to apply container CPU, memory, process and network limits.
7. Keep the bounded request concurrency limit from ADR-039. A new Run attempt remains the retry boundary; the remote worker does not retry internally.

## Consequences

- A capability operation cannot hold a remote HTTP request handler indefinitely beyond the configured wall-clock deadline.
- The remote worker can terminate the isolated capability process without restarting the HTTP service.
- Temporary input/output files are removed after the request.
- The control plane receives a deterministic 504 response for an execution deadline.
- Each request incurs a child-process startup and temporary-file I/O cost; this is accepted for the initial low-throughput remote worker.

## Remaining deployment controls

This does not replace container CPU/memory/process limits, ingress rate limiting, private networking, TLS termination, secret rotation or operational monitoring. The timeout is process-level wall-clock control, not a substitute for container isolation.
