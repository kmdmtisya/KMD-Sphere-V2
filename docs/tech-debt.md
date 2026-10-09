# Technical debt register

Every known shortcut, deferral or workaround is listed here with an owner and the point at which it must be resolved. **Introducing debt without an entry is a defect** (QG-02.6): the pull-request template asks for it. Entries are removed (not edited away) when resolved, with the resolving task in the commit message.

| # | Debt | Why it exists | Risk if left | Owner | Resolve by |
|---|---|---|---|---|---|
| TD-01 | Readiness probe opens its own asyncpg connection instead of using the SQLAlchemy engine | Health endpoint (P01-T07) predates the engine (P01-T08) | Pool settings and TLS options could diverge from real queries | Claude | P05-T01 (first real repository) |
| TD-02 | CI database password is a literal, throwaway value in `backend.yml` | Ephemeral service container reachable only from the job | Secret scanners may flag it; sets a bad pattern | Claude | P12-T06 (GitHub environments / OIDC) |
| TD-03 | iOS CI builds on `macos-latest` with the runner's default Xcode (currently runner image macos-26-arm64); Xcode version is not logged or pinned | Quickest working setup (P01-T10) | A runner image update can change the toolchain and break or silently alter builds | Claude | P14-T02 (release builds) |
| TD-04 | No container images or image scanning yet | Dockerfiles arrive with P12-T04 | Container vulnerabilities cannot be detected until then | Claude | P12-T04 (QG-08.4 is scoped to P12) |
| TD-06 | Required PR approvals are 0 (sole maintainer cannot approve own PRs) | GitHub limitation; compensating controls accepted by the user (ADR-0008) | No independent second human review | User | When a second maintainer joins |
| TD-07 | The gitleaks pre-commit hook needs the `gitleaks` binary on `PATH` and fails closed otherwise | Avoids silently skipping the secret scan | Friction in new shells | Claude | Document per OS (done in CONTRIBUTING); revisit if it blocks contributors |
| TD-08 | HTTP metrics labels come from the FastAPI instrumentation defaults (include `http_host`, `http_server_name`) | Default OpenTelemetry schema | Label cardinality or host leakage in production metrics | Claude | P12-T09 (observability stack) |
| TD-09 | No physical Android device and no iOS device or Mac in the environment | Only emulators are available (docs/quality-targets.md section 1) | Device performance, biometrics and VoiceOver cannot be verified | User | Before P03-T07 |
| TD-10 | GitHub Dependabot security alerts and private vulnerability reporting are not enabled on the repository | Repository settings are owner-controlled | Advisories are not surfaced; `SECURITY.md` reporting channel is not active | User | Before the first external contributor or release |
| TD-11 | Global backend coverage floor is 85%; per-module floors start applying only when business-critical modules exist | No business modules yet | A critical module could land with weak tests until its floor applies | Claude | Each module's first PR (policy in `backend/coverage-policy.toml`) |

## Inline suppressions
Every `noqa` / `type: ignore` carries a rule code and is limited to these justified cases. Adding a new kind requires a line here.

| Suppression | Where | Justification |
|---|---|---|
| `RUF012` | `app/db/base.py` | SQLAlchemy's documented declarative `type_annotation_map` pattern |
| `B008` | tests using FastAPI `Depends(...)` defaults | FastAPI dependency-injection idiom |
| `type: ignore[no-untyped-call]` / `[arg-type]` / `[call-arg]` | tests and `scripts/export_openapi.py` | Untyped SQLAlchemy DDL helpers; settings built from a dict of overrides |
| `S603`, `S314`, `S405` | `scripts/coverage_by_module.py`, one test | Subprocess and XML parsing of files produced by our own CI steps |
| `PLC0415` | `scripts/export_openapi.py` | Imports are deferred until `sys.path` points at `backend/` |
| `E731` | `scripts/track.py` | Small local lambdas |
| `fmt: skip` | `tests/test_redaction.py` | Keeps a parameter table readable |
