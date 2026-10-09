## Task
<!-- Task ID(s) from TASK_CHECKLIST.md, e.g. P05-T04. One task per PR where possible. -->

## Summary
<!-- What changed and why. Link ADRs or docs updated. -->

## Definition of Done (CLAUDE.md)
- [ ] Acceptance criteria of the task pass (evidence below)
- [ ] Relevant tests added or updated and passing; no test deleted or weakened to pass
- [ ] Authorization boundaries preserved (ownership checks, IDOR tests for new endpoints)
- [ ] Financial calculations are deterministic, use Decimal, follow ADR-0006 and are tested
- [ ] API changes have typed schemas; `backend/openapi.json` regenerated and lint-clean
- [ ] Database changes have an Alembic migration with a tested downgrade (single head)
- [ ] Mobile: loading, error, empty and offline states exist; light/dark, 2.0x text and RTL checked
- [ ] Mobile money is `Decimal`/strings; no financial maths or invented data in the client
- [ ] Logs and metrics added where appropriate; nothing sensitive is logged
- [ ] No secrets, tokens or real personal data committed
- [ ] AI changes: tools authorised server-side, structured output validated, no guaranteed-return language
- [ ] Documentation updated (README, docs/, ADR if a decision changed)
- [ ] Any technical debt or new lint/type suppression is recorded in docs/tech-debt.md (no unexplained debt)

## Quality gates
<!-- Criteria verified or affected, e.g. QG-03.1. Verified with `python scripts/track.py qg check ... --evidence ...` -->

## Evidence
<!-- Commands run and their results (format, lint, types, tests, builds), screenshots for UI. -->

## Risks and follow-ups
<!-- Anything unfinished, assumptions made, or decisions needed. Be explicit about failures. -->
