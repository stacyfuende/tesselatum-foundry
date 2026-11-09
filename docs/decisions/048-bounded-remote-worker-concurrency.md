# ADR-048: Bound concurrent remote capability executions

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The authenticated remote worker executes CPU- and memory-intensive geospatial operations. A burst of valid requests could start many simultaneous Shapely/PyProj operations and exhaust the worker container. A process-level bound is required even when ingress also provides connection and rate limits.

The HTTP service uses `ThreadingHTTPServer`, so it must parse a request before returning a well-formed overload response. A hard semaphore at socket acceptance would close connections while clients are still sending bodies and can produce broken-pipe errors instead of a valid HTTP response.

## Decision

1. Bound active capability executions with a process-local `threading.BoundedSemaphore`.
2. Default to two concurrent executions.
3. Configure the limit through `FOUNDRY_MAX_CONCURRENT_EXECUTIONS`; accept values from 1 through 64 and fail startup for invalid values.
4. Parse and validate the incoming request before attempting to acquire an execution slot.
5. When capacity is exhausted, return HTTP 503 with `Retry-After: 2`; do not queue arbitrary work in memory and do not begin another capability operation.
6. Keep the listen backlog bounded at 16 connections.
7. Continue to require ingress-level connection/rate limits, private networking, TLS termination, and container CPU/memory/process/network policies. The execution semaphore is an additional guard, not a replacement for those controls.
8. Do not automatically retry a rejected execution in the same Run. A retry remains a new Run attempt under ADR-014.

## Consequences

- The number of active geospatial capability operations is bounded by a configured process-level limit.
- Overload is represented as a valid HTTP response instead of abruptly closing an in-flight request.
- The server may still create lightweight request-handler threads to parse and reject requests; ingress connection limits remain necessary.
- The default is intentionally conservative for geospatial workloads. Operators should raise it only after measuring CPU and memory under representative data sizes.

## Known limitation

This decision bounds active operations, not the total number of lightweight HTTP handler threads under a connection flood. Ingress connection/rate limits are still required. Per-execution wall-clock termination is addressed separately by ADR-049.
