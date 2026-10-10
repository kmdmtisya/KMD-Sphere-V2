# UX Gate 2 — QA record (P03)

Screens: Home (3), Portfolio Overview (4), Compounding Calculator (9), Wealth Forecast (10), AI Wealth Copilot (6), all on DEMO data. This file records what was checked, how, and on what. Nothing is marked done unless it was actually run.

## 1. Automated journeys (integration_test)

Run: `flutter test integration_test/app_test.dart -d <device-id>` from `mobile/wealthsphere_app`. It runs the real app with the real asset bundle and on-device SharedPreferences. CI has no emulator, so this is run locally.

| # | Journey | Android emulator (sdk gphone16k x86_64, Android 17 / API 37), 2026-10-10 | iOS |
|---|---|---|---|
| 1 | Launch → visit all 5 tabs → nested screen survives a tab switch | Pass | Not run (no iOS device or Mac; TD-09) |
| 2 | Home → Customise → reorder and hide → restart (fresh widget tree on the same storage) → persisted | Pass | Not run |
| 3 | Portfolio → switch to Growth → change period → View all holdings → back | Pass | Not run |
| 4 | More → Calculator → invalid then valid input → Forecast → switch scenario → Today's money → Ask AI (forecast scope carried) | Pass | Not run |
| 5 | AI → suggested question → streamed four-section answer → failure script → Retry | Pass | Not run |

"Restart" in journey 2 rebuilds the app from scratch in the same process on the same on-device storage; a real process kill and relaunch is a manual check below.

## 2. Automated accessibility sweep

`test/a11y/accessibility_sweep_test.dart`, runs in CI with the widget tests: each of the five screens (AI with a conversation on screen) in light and dark, LTR and RTL, at 1.0x and 2.0x text, against:

- Flutter `androidTapTargetGuideline`, `iOSTapTargetGuideline`, `labeledTapTargetGuideline`, `textContrastGuideline`;
- a stricter project tap-target check (`test/helpers/strict_tap_target.dart`), because Flutter's tap-target guideline skips most nodes inside scrolling screens;
- `CustomMinimumContrastGuideline` over every `Text`, because Flutter's `textContrastGuideline` only checks text whose semantics label equals a single `Text` widget (text merged into cards is skipped).

The test view is sized to the whole screen (Flutter's guidelines ignore anything outside `FlutterView.physicalSize`). Each extra check was proven by a deliberate defect: a 24 dp legend row, an unlabelled button and 1.23:1 text were all reported. Result: 40 of 40 pass.

Contrast of every colour role in both themes is also enforced at token level (`test/shared/design_system/tokens/contrast_test.dart`).

## 3. Manual device checklist

Status values: Pass · Fail (with note) · Not run.

Results below were run and reported by the user on 2026-10-10 ("tested all and all passed"). They were not observed by Claude, and the exact device models were not recorded; add them here if needed.

| Check | Small Android (360×640) | Large Android | iPhone SE size | iPhone Pro Max size |
|---|---|---|---|---|
| Notch, status bar and safe areas | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Keyboard: calculator fields visible above it, Next/Done order | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| TalkBack / VoiceOver walkthrough of all five screens (incl. chart summaries) | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Dark mode visual check | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Reduced motion (skeleton static, no chart animation) | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Long strings (pseudo-locale) | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Real restart: customise Home, kill app, relaunch | Pass (user) | Pass (user) | Pass (user) | Pass (user) |
| Side-by-side with `docs/design/wealthsphere-ui-concept.png` | Pass (user) | Pass (user) | Pass (user) | Pass (user) |

Note on long strings: the app ships English only, so the pseudo-locale cannot yet change any app text; this row will need repeating once a second language is added.

## 4. Defects found and fixed during P03

| Found by | Defect | Fix |
|---|---|---|
| Layout matrix | Home app bar actions, insight title and goal rows overflowed at 2.0x on 320 dp | Icon action, flexible text, stacked goal row |
| Layout matrix | Forecast breakdown legend overflowed at 2.0x | Flexible amount |
| Layout matrix | AI screen's pinned chip, composer and footer overflowed under the tab bar on a small phone at 2.0x | Chip and footer scroll with the conversation when space is tight |
| Widget tests | Calculator: invalid fields offscreen (lazy list) or in the collapsed advanced section were not validated and could be submitted | Non-lazy form, fields kept mounted, all-field validity check |
| Widget tests | Strict decimal parsing accepted impossible dates (Dart rolls 2026-13-45 over) | Explicit calendar range checks |
| Integration journeys | AI: a new answer appeared below the fold with no scrolling | Conversation follows the newest turn (instant with reduced motion) |
