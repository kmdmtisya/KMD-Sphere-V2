# QG-24 (QG-FXCUR-04): Android and iOS — P11-T10, 2026-10-13

| Criterion | Evidence | Result |
|---|---|---|
| 24.1 Currency selector functions correctly | `test/features/currency/currency_test.dart`: search, recent currencies, empty result, save, a failed save keeps the current currency; e2e journey 8 chooses EUR against the real backend | Pass |
| 24.2 Converted figures update throughout the app | After a switch every reporting figure is requested again (provider test); e2e journey 8: Home shows the server's net worth in EUR | Pass |
| 24.3 Currency preference persists and syncs | Server-stored setting (`/me/currency-preferences`); backend two-session test; demo mode keeps it on the device and says so | Pass |
| 24.4 Dark and light modes work | Converter in the accessibility sweep (light/dark × LTR/RTL × 1x/2x) and guideline tests in dark and light | Pass |
| 24.5 Loading and error states are tested | Selector loading and error, empty search, failed save; converter validation and failure; status unavailable | Pass |
| 24.6 Flutter tests pass | 1,755 tests pass; analyze and format clean (P11-T07, re-run in P11-T09) | Pass |
| 24.7 Android and iOS builds pass | CI on PR #131 (P11-T07): `android debug build` pass, `ios compile (no codesign)` pass, `format, analyze, test (incl. goldens)` pass. **Limit:** builds only; device runs belong to release (P17) | Pass |
