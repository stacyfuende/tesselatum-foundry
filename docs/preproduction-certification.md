# Foundry pre-production certification

**Purpose:** prove the customer product path and its software contracts before provisioning production cloud infrastructure.

This is a software certification process, not a declaration that a local environment is production-safe. It deliberately separates evidence that can be generated without a cloud account from evidence that requires a real hosted environment.

## Run locally

Install the development dependencies once:

```bash
python -m pip install -r requirements-dev.txt
```

Run the local certification:

```bash
python scripts/preproduction_certify.py --profile local
```

The local profile runs:

1. Ruff lint.
2. JSON Schema, fixture, Capability and implementation-manifest validation.
3. The full pytest suite.
4. An isolated package-install check proving that the installed distribution contains and resolves its schemas, product template, Capability contracts and implementation manifests.

It writes a machine-readable report to `build/preproduction-certification.json` (the build directory is ignored by Git). A non-zero exit code means at least one required local gate failed.

The local profile does not require a cloud account or Docker. Docker-backed tests are skipped unless the worker image environment is configured. The report explicitly records that limitation.

## Full CI profile

CI runs the same certification command with a PostGIS service and Docker:

```bash
FOUNDRY_POSTGIS_DSN=postgresql://postgres:postgres@localhost:5432/foundry \
python scripts/preproduction_certify.py --profile ci
```

The CI profile:

- Requires Docker and a reachable PostGIS service.
- Builds both worker images from the repository Dockerfiles.
- Runs the full test suite with Docker-backed product execution enabled.
- Repeats the isolated installed-distribution check.
- Produces the same JSON report.

The separate live Nairobi Sentinel-2 raster smoke test remains a network-dependent CI job. It is intentionally not silently folded into the local profile.

## What a passing report proves

A passing local report establishes that the code, schemas, package contents and locally runnable automated tests pass on that machine. A passing CI report additionally establishes that the worker images build and the Docker/PostGIS integration suite passes in the CI environment.

The existing tests include authenticated HTTP submission, rejection before tenant resolution for invalid credentials, tenant runtime separation, bounded request handling, exact-origin CORS, accepted-product ZIP delivery and independent verification of the resulting product contents.

## What it does not prove

Neither profile certifies:

- A real browser-driven interaction from the customer page. Current browser-page checks validate element IDs and JavaScript syntax; they are not a browser automation test.
- Production identity-provider configuration, token issuance, revocation or rotation.
- Cloud IAM and object-level tenant isolation.
- TLS, ingress limits, rate limiting, network egress policy or deployment secrets.
- Multi-instance coordination, durable hosted storage, backup restoration or retention enforcement.
- Hosted queue behaviour, customer concurrency, operational alerting or incident response.
- Actual cloud cost per customer product.

These are explicit release gates, not assumptions hidden behind a green test suite.

## Customer acceptance evidence still required

Before opening paid customer access, retain evidence for:

1. A browser-driven happy path and negative paths against a local or preview API.
2. Cross-tenant denial for source files, Runs, Artifacts and downloads.
3. Duplicate submission and retry behaviour.
4. Worker termination, interrupted publication and recovery behaviour.
5. Representative customer datasets, including agreed maximum size and processing time.
6. Independent product review and a reproducible acceptance report.
7. Cost measurements for processing, storage, retention and delivery.
8. A tested backup/restore and deletion procedure.
9. Final hosted-environment smoke tests after deployment.

## Release decision

A local or CI pass is necessary but not sufficient to provision production. Cloud provisioning begins only after the customer workflow, security model, product acceptance criteria, retention policy and cost envelope have been approved. The first cloud deployment should then be a small, controlled production-candidate environment, not an open public launch.
