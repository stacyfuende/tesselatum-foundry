# ADR-004: Separate control and compute planes with portable worker protocol

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Foundry must support local development and cloud execution without coupling scheduling and domain state to a particular compute environment.

## Decision

Separate the control plane from the compute plane. Define one logical Run specification and worker protocol. v0.1 targets a LocalDockerWorker for local/development execution and a simple RemoteWorker protocol over HTTP for cloud execution.

Workers advertise supported implementations, resource limits, and runtime constraints. The scheduler chooses only a compatible worker.

## Consequences

- The control plane does not depend on worker location.
- Local and remote paths can be tested against the same protocol.
- Worker identity, capability support, and runtime digests become part of provenance.
- Remote execution adds security, transport, authentication, and failure-handling work; it must remain deliberately simple.

## Alternatives considered

- Local-only: rejected because it would not validate the portability boundary.
- Cloud-only: rejected because it slows local development and makes the first execution path unnecessarily infrastructure-dependent.
- Kubernetes-first: rejected as premature operational complexity.
