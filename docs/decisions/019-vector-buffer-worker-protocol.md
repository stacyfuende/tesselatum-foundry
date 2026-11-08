# ADR-019: Separate the vector.buffer worker protocol from Docker

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

The first Run service used the concrete Docker adapter as its type and imported the worker result from that adapter. That makes the control plane depend on one deployment mechanism. It also makes a future remote worker or a different execution adapter appear to require changes to the Run service, even though the operation result contract is unchanged.

## Decision

1. Define a typed `VectorBufferWorker` protocol in the execution domain. It describes the implementation identity, worker identity/type, immutable runtime image digest lookup, and execution method required by the Run service.
2. Define `WorkerResult` in the protocol module, not in the Docker adapter. The result is an untrusted transport envelope; the control plane remains responsible for validating it.
3. Make `DockerWorker` one implementation of this protocol. The Run service depends on the protocol, not the Docker class.
4. Include the exact Capability version in the worker request. The current Shapely worker explicitly accepts `vector.buffer@1.0.0` and rejects unsupported versions.
5. The worker reports its implementation and worker identity through the protocol. The Run records those values alongside the immutable runtime image ID digest.
6. Keep this protocol capability-specific until a second real worker adapter demonstrates which concepts are genuinely common. Do not introduce a generic arbitrary-capability plugin interface prematurely.

## Consequences

A fake worker can exercise Run state transitions and output validation without Docker, while the same Run service can later accept another adapter that implements the protocol. The current protocol does not itself provide remote transport, authentication, scheduling, worker discovery, or a generic execution manifest registry. Those remain separate concerns and require their own contracts and tests.

## Alternatives considered

- **Keep the Run service typed directly to DockerWorker:** rejected because it couples the control plane to a local container implementation.
- **Create a generic worker protocol for all future capabilities now:** deferred because only one executable capability has been integrated; premature generalization would encode assumptions not yet tested.
- **Let the worker decide whether its output is valid:** rejected; worker output remains untrusted and is checked independently by the control plane.
