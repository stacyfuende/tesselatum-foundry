# ADR-026: Snapshot implementation manifest integrity in each Run

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

A Run records an implementation ID and version, while the implementation registry stores the engine, runtime, supported capability version, and conformance evidence. An ID/version pair is only a stable reference if the manifest contents for that version remain unchanged. The initial repository-backed registry does not yet provide signed manifests or an immutable remote registry.

For reproducibility and audit, the Run must identify the exact manifest content that was used when dispatch was authorized.

## Decision

1. Canonicalize a registered implementation manifest as UTF-8 JSON with sorted keys, compact separators, and non-finite numbers disallowed.
2. Compute SHA-256 over those canonical bytes.
3. Require the Run's implementation provenance object to include the 64-character manifest checksum alongside implementation ID and version.
4. Compute the checksum from the registry's detached manifest copy; callers cannot alter the registry's stored object by mutating a returned manifest.
5. Keep the runtime image ID digest as a separate field. The manifest checksum identifies the declared implementation metadata; the image digest identifies the concrete container image used for that Run.

## Consequences

A Run can distinguish two different manifest contents even if an operator accidentally edits a manifest without changing its ID/version. The checksum does not authenticate who published the manifest or prove that the image was built from reviewed source. Signature verification and immutable remote registry controls remain future work.

## Alternatives considered

- **Record only implementation ID and version:** rejected because manifest content could change while retaining the same reference.
- **Use the runtime image digest as the only implementation identity:** rejected because the image digest does not capture the full contract/conformance declaration.
- **Add the manifest checksum to the Capability contract:** rejected because the implementation is separately versioned from the engine-independent Capability.
