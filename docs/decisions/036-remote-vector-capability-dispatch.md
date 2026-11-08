# ADR-036: Remote worker service supports exact vector capability dispatch

- **Status:** Accepted
- **Date:** 2026-11-08
- **Supersedes:** The buffer-only deployment boundary recorded in ADR-032 and ADR-035, without changing their original historical decisions.

## Context

ADR-032 introduced an authenticated HTTP transport for `vector.buffer@1.0.0`. ADR-035 added a second operation, `vector.reproject@1.0.0`, but intentionally left it local-Docker-only. The second independently implemented operation now demonstrates that the remote transport's common concerns are stable: authenticated identity, exact capability/version declaration, implementation identity, immutable runtime image digest, bounded JSON transport, and an untrusted FeatureCollection result envelope.

## Decision

1. Extend the existing remote worker service to support exactly `vector.buffer@1.0.0` or `vector.reproject@1.0.0`, selected by deployment configuration. A worker process advertises one exact capability/version pair; it does not dynamically advertise or execute arbitrary capabilities.
2. Keep `vector.buffer` and `vector.reproject` request semantics explicit and distinct. Buffer requests include a measurement CRS; reprojection requests include a target CRS. Do not normalize these into an untyped generic parameter bag.
3. Advertise the exact implementation ID for the selected capability in the authenticated identity response. The control plane must still resolve the canonical manifest and require passed conformance.
4. Preserve the existing bearer authentication, HTTPS requirement, redirect rejection, payload bounds, timeout behavior, immutable runtime digest pinning, and host-side independent output critic.
5. Deploy one process per capability/version. Operators configure `FOUNDRY_WORKER_CAPABILITY_ID`, `FOUNDRY_WORKER_CAPABILITY_VERSION`, and optionally `FOUNDRY_IMPLEMENTATION_ID`; defaults remain vector.buffer@1.0.0 for backward compatibility.
6. Keep TLS termination, private network isolation, container resource limits, secret rotation, and multi-tenant authorization outside this worker process. This remains a private execution service, not a public API.

## Consequences

- Both vector capabilities can execute through local Docker or authenticated remote HTTP workers.
- The same remote worker image can be deployed with distinct exact capability identities.
- A misconfigured client/server capability pair fails during identity preflight or request dispatch, before successful Run completion.
- Capability-specific input semantics and output critics remain in the control plane and worker implementations.
- Remote worker discovery, multi-capability worker processes, automatic failover, and public multi-tenant authorization remain out of scope.

## Alternatives considered

- **Advertise all supported capabilities from one worker process:** rejected for now because per-capability implementation identity and runtime provenance should remain unambiguous.
- **Accept arbitrary capability IDs in requests:** rejected because the deployed worker identity must constrain execution.
- **Make reprojection requests look like buffer requests:** rejected because target CRS and measurement CRS are different semantic contracts.
- **Expose the service publicly as a multi-tenant API:** deferred; ingress authentication and authorization require a separate control-plane design.
