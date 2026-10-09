# ADR-0007: Test strategy

Status: Proposed

## Decision
- **Backend:** pytest unit tests; API integration tests against PostgreSQL and Redis service containers; golden and property-based (Hypothesis) tests for financial engines; authorization/IDOR tests for every protected endpoint; provider contract tests using recorded fixtures.
- **Mobile:** widget tests through `pumpApp` (light/dark, 2.0x text, RTL); golden tests tagged `golden`, authoritative on CI ubuntu; Riverpod state tests; `integration_test` journeys on an emulator.
- **AI:** structured-output validation, prompt-injection, cross-user, tool-permission, hallucination-regression and stale/missing-data suites, with documented evaluation datasets.
- **Coverage:** reported per module. Target at least 85% line coverage for business-critical backend modules (QG-03.5) without treating coverage as a substitute for meaningful tests. Critical financial calculations require 100% requirement/edge-case coverage through documented test cases (QG-03.4).
- Tests are never deleted or weakened to make a build pass.

## Consequences
QG-03, QG-06 and QG-07 get concrete evidence sources, and CI time is managed with path filters.
