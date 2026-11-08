# ADR-032: Authenticated HTTP transport for remote vector.buffer workers

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The control plane now dispatches Recipe nodes through exact capability-version runners, but the only executable worker adapter was local Docker. A remote adapter is needed to verify that a Run service can execute the same capability contract without sharing the control plane's host or Docker daemon.

## Decision

1. Keep the transport capability-specific. The first remote endpoint executes only `vector.buffer@1.0.0`; this does not establish a generic worker protocol for arbitrary future capabilities.
2. Expose an authenticated identity endpoint and an execution endpoint. Identity includes worker and implementation identifiers plus the immutable runtime image digest. Execution includes the exact capability version, input FeatureCollection, CRS declarations, and normalized parameters.
3. Require a bearer token for both endpoints. The client requires HTTPS, rejects redirects, bounds request and response sizes, applies a finite timeout, and verifies that the runtime digest returned by execution matches the digest pinned during preflight.
4. Treat all remote output as untrusted. The existing Run service remains responsible for independent output validation, Artifact persistence, provenance, and lifecycle transitions.
5. Keep the HTTP service behind a trusted TLS ingress on a private network. Deploy it in a constrained container with resource and network policies. The service itself does not terminate TLS or provide multi-tenant authorization.
6. Require operators to configure the exact immutable runtime image digest exposed by the worker. A mutable tag is not sufficient provenance.

## Consequences

- The same vector.buffer Run service can use local Docker or a remote HTTP worker without changing the Capability contract.
- Worker identity and runtime image provenance remain visible to the control plane.
- Authentication, transport bounds, redirect rejection, and digest pinning are enforced by the adapter.
- Production deployment still requires TLS ingress, secret rotation, private networking, container resource limits, and operational monitoring.
- The adapter is not a generic distributed scheduler and does not yet provide remote worker discovery or automatic failover.

## Alternatives considered

- **Expose an unauthenticated worker endpoint:** rejected because spatial inputs and compute resources must not be available to arbitrary callers.
- **Allow arbitrary HTTP endpoints:** rejected because credentials and input data must be protected in transit; insecure HTTP is limited to explicit localhost tests.
- **Trust the remote worker's output:** rejected; remote output remains untrusted and is independently validated by the control plane.
- **Generalize transport across all capabilities immediately:** deferred until a second capability demonstrates the common request and result semantics.
