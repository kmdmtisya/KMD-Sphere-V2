# ADR-0008: Quality-gate policy and merge protection

Status: Proposed (decision on review rules requested from the user)

## Context
QUALITY_GATES.md defines 12 platform quality gates (QG-01..QG-12). They only mean something if failing checks block merges and if evidence is recorded honestly. The repository is public and currently has one maintainer; commits are authored with that maintainer's GitHub account.

## Decision
**1. Merge protection (GitHub ruleset "main protection", no bypass actors).** Changes to `main` go through a pull request. Force-pushes and deletion of `main` are blocked. The following status checks are required and must pass:

| Required check | Source | Meaning |
|---|---|---|
| `backend gate` | `backend.yml` | lint, strict types, OpenAPI contract and Spectral, migrations, tests, coverage floors |
| `mobile gate` | `mobile.yml` | format, analyze, tests incl. goldens, Android build, iOS compile |
| `security gate` | `security.yml` | gitleaks, dependency audit, CodeQL, Trivy, SBOM |
| `tracker validate` | `tracker.yml` | task, dependency, quality-gate and timestamp consistency |

**2. Gate jobs instead of path filters.** Each workflow always runs, decides whether its area changed (defaulting to "run" whenever it cannot prove otherwise), and reports through one always-present gate job. A required check therefore never waits forever on a path-filtered workflow, and a heavy job that is wrongly skipped fails the gate.

**3. Reviews.** GitHub cannot require an approving review that the pull-request author is unable to give: the AI-authored changes are pushed with the maintainer's own account, and a user cannot approve their own pull request. The ruleset therefore requires **zero approving reviews** and compensates with:
- CODEOWNERS requesting the maintainer on every pull request (and explicitly on `.github/`, `backend/app/core/`, migrations, security docs, the tracker and the quality-gate register);
- the pull-request template's Definition of Done checklist;
- mandatory user approval (recorded by the tracker with `--approved-by`) for every task flagged *Approval: yes* and for every phase gate;
- an independent review pass of the diff before a task that touches money, authorization, AI tools or migrations is completed.
When a second human maintainer joins, raise required approvals to 1 and require code-owner review.

**4. Evidence.** Gate criteria are ticked only with `track.py qg check ... --evidence ...`; CI repeats the automated parts. Release workflows call `track.py qg require` (P12-T08).

**5. Waivers.** Only non-critical criteria can be waived, with justification, approver, risk owner and expiry (QUALITY_GATES.md). Critical security, financial-integrity and authorization criteria are never waived by the tracker.

## Consequences
- Every change, including tracker-only updates, is a pull request and waits for the checks. Tracker-only pull requests are quick because the backend and mobile gates skip their heavy jobs.
- The owner cannot push directly to `main`; relaxing the ruleset is a deliberate, visible settings change.
- QG-02.5 ("code reviews are completed for relevant changes") is satisfied by the compensating controls above only if the user accepts them; that decision is recorded in EXECUTION_LOG.md.
