# ADR-039: Bound concurrent remote worker requests

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The authenticated remote worker uses `ThreadingHTTPServer`. Each accepted request creates a handler thread, and a handler can execute a CPU- and memory-intensive geospatial operation. Authentication, request-size limits and a client timeout do not bound the number of concurrent server threads. A valid but misbehaving client, leaked bearer token or accidental burst could exhaust the worker container before its CPU and memory limits provide a predictable response.

## Decision

1. Replace the unbounded threaded server with a bounded threaded HTTP server.
2. Limit all concurrent request handlers using a process-local bounded semaphore. The default is two concurrent requests.
3. Configure the limit through `FOUNDRY_MAX_CONCURRENT_REQUESTS`; accept values from 1 through 64 and fail startup for invalid values.
4. When capacity is exhausted, reject the connection with HTTP 503 and `Retry-After: 2`; do not queue arbitrary work in memory.
5. Keep a bounded listen backlog of 16 connections.
6. Continue to require ingress-level rate limiting, private networking, TLS termination, and container CPU/memory/process limits. The in-process semaphore is an additional guard, not a replacement for deployment isolation.
7. Do not automatically retry a rejected execution in the same Run. A retry remains a new Run attempt under ADR-014.

## Consequences

- Concurrent request threads and capability executions are bounded by a configured process-level limit.
- Overload is explicit and observable rather than silently accumulating threads.
- The control plane can treat HTTP 503 as temporary worker unavailability.
- The default limit is intentionally conservative for geospatial workloads; operators may raise it only after measuring memory and CPU under representative data sizes.

## Known limitation

This decision does not yet impose a hard per-execution wall-clock limit inside the remote worker process. The client timeout bounds how long the control plane waits, but a timed-out server-side operation may continue until it finishes or the container is terminated. Process-level execution timeout and graceful shutdown remain separate hardening work.
