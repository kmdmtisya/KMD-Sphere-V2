# UX Gate 3 — QA record (P07)

Screens (13, all on DEMO data): Welcome (1), Sign in (2), Home (3), Portfolio (4), Investments/Holdings (5), AI Wealth (6), Investment Details (7), Transactions (8, with add flow, entry detail and correction), Compounding Calculator (9), Wealth Forecast (10), Financial Goals (11, with detail and add/edit), Portfolio Doctor (12), AI Investment Opportunities (13, with research sheet and comparison). Also the More hub, Net Worth, Income and Settings. Nothing is marked done unless it was actually run.

## 1. Automated journeys

Journeys 1 to 5 are the Gate 2 journeys (docs/design/qa-gate2.md). Journeys 6 to 10 are new:

| # | Journey |
|---|---|
| 6 | Portfolio → all holdings → search and clear → asset-class filter → open an investment (no trade action) → its Transactions section → open an entry → back, back |
| 7 | Portfolio → Transactions (a corrected entry is marked) → Add transaction → inline errors → valid trade → review → save → confirmation → view → correct (a linked reversal is added) → Add corrected entry (prefilled) |
| 8 | Goals → Add goal → inline errors → valid goal → opens with no invented estimate → edit → assumptions shown |
| 9 | AI Wealth → Portfolio Doctor → filter → scenario sheet → back → Opportunities (DEMO notice) → research sheet → compare two ideas → back → Simulate → calculator pre-filled and marked → Calculate → forecast |
| 10 | More (Coming soon entries) → Net worth → Income → Settings → Light/Dark/System theme → back |

Two runs of the same flows:

- **CI, every pull request:** `test/journeys/gate3_journeys_test.dart` drives the real router and shell (5 tests, passing).
- **Device:** `flutter test integration_test/app_test.dart -d <device-id>` from `mobile/wealthsphere_app`, real asset bundle and on-device storage. CI has no emulator, so this is run locally.

| Journeys | Android emulator (sdk gphone16k x86_64, Android 17 / API 37), 2026-10-12 | iOS |
|---|---|---|
| 1 to 10 | Pass: 10 of 10 in the final full run | Not run (no iOS device or Mac; TD-09) |

Honest run history on the emulator: the first full run after the emulator was started failed journey 1 (tab taps did not land while the cold emulator was still settling) and journey 5 (an unmounted-provider error because the demo copilot stream outlived the test; fixed with a `ref.mounted` guard in `DemoCopilotRepository`). Journey 1 then passed in the next full run and in two further isolated runs, and failed once more in an isolated run before that; the cause of that single failure was not isolated, so it is recorded as an emulator timing flake, not as explained.

## 2. Automated accessibility sweep

`test/a11y/accessibility_sweep_test.dart` now sweeps 24 screens and states (Gate 2's five plus Holdings, four Investment Details sections, Transactions, Transaction detail, Add transaction with errors, Goals, Goal detail, Goal form with errors, Portfolio Doctor, Opportunities with the comparison bar, Compare, More, Net worth, Income, Settings with and without a device lock) in light and dark, LTR and RTL, at 1.0x and 2.0x text: 192 tests, all passing. Checks are those of Gate 2 (Flutter tap-target, label and contrast guidelines, the stricter project tap-target check, contrast over every `Text`). Welcome and Sign in are swept in `test/features/auth/auth_screens_test.dart`. Every new screen also has its own guideline tests in light/dark, 1x/2x and LTR/RTL.

## 3. Manual device checklist

Status values: Pass · Fail (with note) · Not run. **Nothing below has been run by anyone yet.** It is for the user's device pass at the gate.

| Check | Small Android | Large Android | iPhone SE size | iPhone Pro Max size |
|---|---|---|---|---|
| Safe areas and notch on the new screens | Not run | Not run | Not run | Not run |
| Keyboard on the add transaction and goal forms (fields visible, Next/Done order) | Not run | Not run | Not run | Not run |
| Date picker usable with TalkBack / VoiceOver | Not run | Not run | Not run | Not run |
| Screen reader walkthrough of the new flows (chips, forms, sheets, comparison) | Not run | Not run | Not run | Not run |
| Dark mode visual check of all new screens | Not run | Not run | Not run | Not run |
| Large text (2x) on forms and sheets | Not run | Not run | Not run | Not run |
| RTL spot check | Not run | Not run | Not run | Not run |
| Reduced motion | Not run | Not run | Not run | Not run |
| Side-by-side with `docs/design/wealthsphere-ui-concept.png` | Not run | Not run | Not run | Not run |

## 4. Defects found and fixed during P07

| Found by | Defect | Fix |
|---|---|---|
| Accessibility tests | A sideways chip scroller clipped its last chip (tap target too small) | Wrapping chips on Holdings, Transactions, Investment Details, Doctor and Opportunities |
| Layout tests | Health card header, "In comparison" row, More "Coming soon" label and Net worth amounts overflowed at 2x / 320 dp | Wrapping or flexible layouts |
| Widget tests | Investment Details used a scrollable tab bar that hid tabs off screen at 400 dp | Wrapping section chips |
| Widget tests | Demo assets over 50 KB hung `pumpAndSettle` (background isolate under fake async) | Test bundle decodes on the same isolate |
| Journeys | Back from a transaction opened from an investment landed on the ledger, and from a linked entry skipped the one before | Those links are pushed, so Back returns where the user came from |
| Gate 3 sweep | App lock text in Settings fell below contrast when the switch was disabled, and the reason it was off was greyed too | Title and hint keep readable colours |
| Device journeys | Demo copilot stream could outlive its provider at teardown | `ref.mounted` guard |

## 5. Known gaps (carried forward)

- The add transaction form accepts only `.` as the decimal separator (the goal form and calculator use the locale's). The app ships English only; fix before a second language.
- Goals, transactions and watchlist changes in the demo live in memory for the session and are not reflected on Home.
- A rate that is out of range on the server is only caught by the server; the app mirrors the documented limits.
