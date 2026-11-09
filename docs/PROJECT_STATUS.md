# Project status and collaboration guide

**Last updated:** 2026-11-09  
**Status:** Living engineering tracker. Update this document when a capability, validation gate, PR dependency, or operational assumption changes.

This page is the working hand-off for contributors and future sessions. It separates implemented behavior from work that is merely proposed, in review, or not yet verified. A checked implementation item does not imply that its current branch has passed CI or is production-ready. Read [Project vision](PROJECT_VISION.md) for the broader product ambition; this tracker remains the source of truth for implementation status.

## Project intent

Tessellatum Foundry is contracts-first infrastructure for describing, composing, executing, validating, and reproducing spatial computations across engines and execution environments. Its core records are versioned Capabilities, Geo-Cells, Recipes, Runs, Artifacts, and separate Validation Reports.

Engineering principles:
- Capability contracts are canonical and engine-independent; implementations are registered separately.
- Schema validity is not semantic validity or methodological suitability.
- Runs snapshot exact inputs, versions, implementation identity, and provenance.
- Outputs are independently inspected before immutable Artifact registration or cache reuse.
- Fail closed on invalid CRS, geometry, band selection, non-finite data, and unverifiable claims.
- Keep local execution and remote transport boundaries explicit; do not imply a deployment is production-hardened because code exists.

## Current capability and platform inventory

| Area | Implemented / evidenced | Remaining / qualification |
|---|---|---|
| Contracts and registries | JSON Schema validation, semantic Recipe graph validation, canonical Capability registry, conformance-gated implementation registry | Continue contract evolution and installed-package checks for every new capability |
| Vector buffer | Shapely and PostGIS realizations; shared conformance; dedicated Run path and isolated local Docker worker | Broader CRS/geometry edge-case coverage; suitability and authoritative rights/security policy remain outside current evidence |
| Vector reprojection | Shapely/pyproj kernel; dedicated Run path and worker; independent output critic; mixed Recipe use; target-CRS-aware evidence-gated cache | Area-of-use review is proposed in PR #20; not a positional-accuracy guarantee |
| Recipe execution | Deterministic sequential topological execution; upstream Artifact and Run lineage; mixed buffer/reproject Recipe coverage | Parallel scheduling, retries/resume policy, and broader capability families |
| Local SDK | LocalFoundry facade over canonical registries/stores and sequential Recipe execution | Authenticated network API, multi-tenant service boundary, generated client SDK |
| Raster band statistics | Initial kernel, contract, Rasterio/NumPy packaging, independent critic, and generated GeoTIFF tests are proposed in PR #21 | Not yet integrated into Run/Artifact/Recipe lifecycle. The feature branch now processes source blocks incrementally in both the kernel and independent critic, with a multi-tile regression test. This bounds working memory to a source block, but CI verification is still outstanding; very wide striped rasters can still have large blocks. Verify CI and installed distribution before treating the branch as conformant |
| Remote worker | Authenticated HTTPS transport and service exist for vector capabilities | PR #13 concurrency bound and PR #15 process-isolated hard timeouts are open; production ingress, resource policy, monitoring, secret rotation and deployment verification remain |
| Provenance / methodology | Rights declarations and lineage are recorded; buffer approximation and reprojection operation evidence are recorded | Declarations are not proof of legal permission; suitability, authoritative rights policy, security policy and accuracy assessment require additional inputs and governance |

## Active pull requests and dependency notes

All states below are a snapshot; check GitHub before acting.

- [PR #21 — first raster capability: band statistics](https://github.com/stacyfuende/tesselatum-foundry/pull/21) (feat/raster-band-statistics): contract, Rasterio/NumPy kernel, critic, packaging, tests and ADR-044. The contract JSON serialization defect was corrected in commit 0a15c8e916325398902ee231233fdbda4e463789. Windowed kernel/critic processing and a multi-tile regression test were added through commit 3b1505d4baf2332de428dc51ff609c6869e34aac; subsequent commits added non-finite floating-sample coverage, an independent critic pass across a multi-tile raster, and a tampered-output regression test. A malformed literal-newline import in the test module was found during review and corrected; the critic was also tightened to reject boolean values masquerading as integer dimensions, band counts, or pixel counts. Latest PR head known to this tracker: 6823c6422d43b8f4e204e57ecd25cdb2bc852d5d. Added a striped GeoTIFF window-aggregation regression test. GitHub Actions and combined-status queries returned no runs or statuses for this head; do not mark CI as passed. The PR explicitly says its implementation manifest is not_run and that runtime integration is follow-on work.
- [PR #20 — reprojection area-of-use coverage](https://github.com/stacyfuende/tesselatum-foundry/pull/20) (feat/reproject-area-of-use-check): extent-level comparison against PROJ operation area-of-use, including antimeridian-wrapping bounds. This is a methodological warning, not a guarantee of positional accuracy.
- [PR #13 — remote worker concurrency bound](https://github.com/stacyfuende/tesselatum-foundry/pull/13): process-local semaphore and overload response. Verify full CI and container behavior before merge.
- [PR #15 — remote worker hard timeouts](https://github.com/stacyfuende/tesselatum-foundry/pull/15): child-process isolation and server-side timeout. It is stacked on PR #13; synchronize it with the latest PR #13 head, review/merge #13 first, then retarget #15 to main and rerun CI.

PR order: resolve #13 before #15. PR #20 and #21 are independent forward workstreams and need their own CI/review. Do not merge solely because code has been committed.

## Raster statistics: implementation contract and next steps

The proposed raster.band_statistics@1.0.0 contract describes exact per-band statistics over all valid finite stored samples. Nodata and masked pixels are excluded. Scale, offset and unit metadata are reported, not applied. Standard deviation is population standard deviation (ddof=0). A source CRS is required. The initial output includes dimensions, selected band indexes, valid pixel count, minimum, maximum, mean, standard deviation, dtype, scale, offset and unit.

Important implementation observation: the branch initially read each entire band into memory. That has been replaced by source-block iteration in both the kernel and independent critic, with a mergeable accumulator. Working memory is now bounded by a source block and accumulator state, although unusually wide striped rasters may still expose large blocks. Before enabling large-raster workloads:
1. [x] Replace whole-band reads with block/window iteration and a numerically stable mergeable accumulator (count, min, max, mean, population variance) in the kernel.
2. [x] Keep critic validation independently implemented and windowed; it does not call the kernel.
3. [~] Add tiled and striped GeoTIFF tests, internal/external masks, nodata, non-finite floating samples, multiple bands, empty-valid-band behavior, and very large synthetic dimensions. A multi-tile exactness test is now present; broaden the edge-case matrix.
4. [~] Confirm finite output behavior for extreme numeric values. Integer bands now retain exact integer extrema and use per-band integer baselines before float64 variance accumulation, avoiding loss of adjacent int64/uint64 values above 2^53. Mean and standard deviation remain float64 outputs; broader adversarial tests (including uint64 extremes and float64 overflow) remain.
5. If future contract versions add exact quantiles/median, design a bounded-memory exact algorithm (e.g. external selection) or explicitly revise semantics; do not silently substitute approximate quantiles.
6. Only then connect the capability to canonical dispatch, Run lifecycle, Artifact persistence, Recipe execution, cache evidence, and installed package conformance. Remove the not_run gate only after the entire path is validated.

## Remote worker hardening checklist

- [ ] Review/merge PR #13 after full CI and container-level overload test.
- [ ] Rebase/retarget PR #15 onto the merged #13/main history; resolve conflicts and rerun full CI.
- [ ] Exercise timeout behavior in the actual worker container and confirm process-group termination.
- [ ] Confirm Run transitions to timed_out; verify retry creates a new attempt without rewriting prior provenance.
- [ ] Before production: private ingress, TLS, authentication/secret rotation, request and response limits, CPU/memory/process limits, network egress policy, rate limiting, logs/metrics/alerts, and operational runbooks.

## Verification and release discipline

For every PR, record:
- exact head commit SHA;
- required GitHub Actions checks and their final states;
- unit, conformance, integration, Docker/PostGIS and packaging coverage as applicable;
- whether tests were run locally or only in CI;
- known limitations and any manual deployment checks still outstanding.

Do not equate an empty status list with success. Do not claim a CI pass without a completed successful check on the current head SHA. Re-run checks after any commit that changes source, tests, schemas, manifests, or packaging.

## Suggested collaboration workflow

1. Start with this page, [the architecture](../ARCHITECTURE.md), and the [decision register](decisions/README.md).
2. Read the relevant ADR and Capability contract before changing behavior.
3. Keep each PR scoped to one capability or infrastructure concern; state dependencies and non-goals in its description.
4. Add tests at contract, kernel, independent-critic, lifecycle, and packaging boundaries as relevant.
5. Update this tracker in the same PR when status, dependencies, semantics, or next steps change.
6. Preserve explicit not_run / unverified states until conformance and runtime evidence justify promotion.

## Decision and evidence index

- [ADR-043](decisions/043-reprojection-area-of-use-coverage.md): reprojection area-of-use coverage (PR #20).
- [ADR-044](decisions/044-raster-band-statistics.md): raster band statistics scope and semantics (PR #21).
- [ADR-039](decisions/039-methodological-evidence.md), [ADR-040](decisions/040-buffer-arc-approximation.md), [ADR-041](decisions/041-buffer-arc-tolerance.md), [ADR-042](decisions/042-reprojection-operation-evidence.md): methodology and operation evidence.
- [ADR-032](decisions/032-authenticated-remote-worker-transport.md) and [ADR-036](decisions/036-remote-vector-capability-dispatch.md): remote transport and capability dispatch.

---
*This document is intentionally a living tracker, not a substitute for immutable ADRs, PR descriptions, test results, or release records.*


## CI usage policy

The repository CI workflow is intentionally pull-request-first. The full Docker/PostGIS integration suite runs for relevant pull-request changes and can also be started manually with `workflow_dispatch`. It does not automatically repeat the full suite on the merge-to-`main` push, because a normal merge has already been validated on its pull request.

The workflow ignores documentation-only changes and uses a concurrency group with `cancel-in-progress: true`, so a newer commit on the same pull request supersedes an obsolete in-progress run. This reduces wasted hosted-runner time while retaining a full pre-merge integration gate.

For local verification, contributors can run the same component checks and test suite from the repository environment. A self-hosted Actions runner is a possible later option for a trusted, privately controlled machine; do not expose a self-hosted runner to untrusted pull-request code, especially from forks. GitHub documents self-hosted runner usage as not consuming the included hosted-runner minutes, while standard hosted runner usage is free for public repositories. Billing allowances are account-level and may be shared across private repositories owned by the same account.

The current allowance notice should be checked in **Settings → Billing & licensing → Usage** to confirm whether it refers to included compute, legacy minute quota, or storage. Do not infer remaining minutes from an email percentage alone.

## 2026-11-09 implementation hand-off — raster Capability schema repair

- Working branch: `fix/raster-capability-semantics-schema`, based on `feat/raster-band-statistics`.
- Root cause confirmed from failed Actions job 42659912157: the installed-package smoke test loads `raster.band_statistics@1.0.0`, whose normative `semantics` property was rejected by `capability.schema.json` because additional properties are closed.
- Implemented an optional, unique array of non-empty strings as the top-level Capability `semantics` property. Existing contracts remain valid without it; `additionalProperties: false` remains enforced.
- Added a schema regression test that validates the checked-in raster Capability and rejects empty/duplicate semantics entries.
- Recorded ADR-045 and indexed it in the decision register.
- Commits on the working branch: `55aaddf` (schema), `da1d440` (test), `b65f90a` (ADR), `9773077` (ADR index).
- No workflow run was triggered by these commits. Local tests have not been run in this environment. Do not mark PR #21 or the raster implementation conformant until a full required check passes on the final PR head.
- Next: perform read-only review of the resulting diff, run targeted schema tests and the installed-package smoke test in a controlled local environment if available, then decide whether to request one deliberate PR validation run. Preserve the raster manifest state as `not_run`.


## 2026-11-09 implementation hand-off — raster integer precision review

- Read-only review found that both the raster kernel and independent critic converted integer samples directly to float64. Adjacent int64/uint64 values above 2^53 could therefore collapse before min/max and variance were computed.
- Updated the kernel and critic to preserve integer min/max values and subtract a fixed per-band integer baseline using Python integer arithmetic before float64 mean/variance accumulation. The critic compares integer extrema exactly and remains a separate implementation path.
- Added a regression test using adjacent int64 values around 2^60; it checks exact extrema, population standard deviation of the small offsets, and critic acceptance.
- Updated ADR-044 to distinguish exhaustive pixel processing from arbitrary-precision arithmetic: mean and standard deviation remain float64 outputs.
- Commits: kernel 8c24bdd, cleanup 72a8749, and formatting/documentation clarification 6d9c8ab; critic b72e310; regression test a924e97; ADR-044 b5b8876.
- These changes have been committed but not executed in a local Python environment or GitHub Actions. Do not mark the test as passing or the raster implementation conformant until targeted tests and full CI pass.


## 2026-11-09 implementation hand-off — raster validity edge cases

- Corrected the int64 precision regression test's missing pytest import (commit f224713).
- Added coverage for a GeoTIFF internal validity mask combined with NaN and positive-infinity samples. The expected result excludes the masked cell and all non-finite values; the independent critic must accept the result (commits f15fefe and db6e957).
- Added a test that an all-non-finite float band is rejected with the documented no-finite-valid-pixels error.
- These are source-level additions only. They have not been run locally or in Actions. The mask-writing behavior should be confirmed by executing the test in the project's supported Rasterio/GDAL environment.


## 2026-11-09 implementation hand-off — critic robustness

- Hardened numeric validation in the independent raster critic: a tampered output containing an integer too large to convert to float64 is now treated as a failed numeric result instead of risking an uncaught OverflowError (commit 9dee8c0).
- Extended the critic tampering regression to include a 10**1000 minimum value (commit 0e99a12).
- No local Python test run or Actions run has been performed. Keep the validation state provisional until the raster validation tests run in the supported environment.
