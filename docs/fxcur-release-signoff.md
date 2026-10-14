# FXCUR release readiness sign-off (P11-T12)

Feature: multi-currency reporting and FX management (phase P11, tasks P11-T01 to P11-T11). It ships with the core release (P17).

**Status: signed off by the user on 2026-10-13 (P11-T12.3).**

## Acceptance criteria

| Criterion | Evidence | Result |
|---|---|---|
| Provider licence permits the intended display and caching | [fxcur-licence-review.md](fxcur-licence-review.md): ExchangeRate-API and ECB terms read on 2026-10-13. Both permit showing rates to our own signed-in users and storing them for their valuations, provided the source is cited (ECB) and the rates are presented as information only. P11-T12 added the source line wherever rates appear, a permanent information-only note on the converter, and ExchangeRate-API as primary (widget tests; re-run soak) | Met, subject to the two production conditions below |
| Audit retention follows the approved policy; cosmetic UI conversions are not logged as financial records | DEC-28: AI answers (`ai_answer`), reports and converter use (`converter`) are audited; the database rejects any other type, including `display_switch`; the audit is append-only (`tests/fx/test_currency_schema.py`). New test `test_switching_and_viewing_in_a_currency_is_not_audited_but_the_converter_is`: three currency switches and reading every translated screen write no audit row; one converter use writes exactly one. Retention follows the audit policy, which P16-T05 sets; its acceptance criteria now name `fx_conversion_audit` explicitly | Met |

## Quality gates and validation

- QG-21 to QG-25 passed (P11-T10, `reports/quality/qg-21` to `qg-25`).
- Integration report: [fxcur-integration-report.md](fxcur-integration-report.md) (P11-T09).
- Soak report: [fxcur-soak-report.md](fxcur-soak-report.md) (P11-T11, re-run at P11-T12 with the final provider order). Every check passed.

## Decisions recorded (user, 2026-10-13)

| Decision | Outcome |
|---|---|
| Budget (DEC-25) | ExchangeRate-API Pro, about USD 10 a month, approved |
| Licence confirmation | Ask ExchangeRate-API in writing before production; draft email in the licence review |
| Display gaps | Fixed in P11-T12: source named on every rate display; information-only note on the converter |
| Provider order | ExchangeRate-API first, ECB as fallback |
| Audit retention (DEC-28) | Follows the audit policy, set in P16-T05 (now an explicit acceptance criterion there) |

## Conditions before production (tracked, not blocking P11)

1. Buy the ExchangeRate-API Pro plan and store its key as a secret (`EXCHANGERATE_API_KEY`), never in source.
2. Receive ExchangeRate-API's written confirmation of the use described in the licence review.
3. Run the real-provider soak (P14-T11): quota counting, latency and publication times against the live service.
4. Re-check both providers' terms before release (P17); their terms can change.

## Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Product owner | user (mtisya@gmail.com) | 2026-10-13 | Signed off: ready to ship with the core release (P17), subject to the conditions before production above |
