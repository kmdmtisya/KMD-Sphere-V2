# Web portal accessibility report (WCAG 2.2 AA)

**Status:** P14-T19, 2026-10-16. **Automated and scripted checks: complete. Manual screen-reader passes: not done** (see below). Because of that, QG-27.6 ("automated and manual") is not claimed.

## What was run

All of it in Chromium against the real stack (`web/e2e/a11y.spec.ts`, plus the per-module specs, each of which also runs axe in Light and Dark).

| Check | Scope | Result |
|---|---|---|
| axe-core (WCAG 2.0 A and AA, 2.1 AA, 2.2 AA) | Every page in the navigation (15 routes) and the operator page, each in Light and Dark | No serious or critical violation |
| axe on open overlays | Command palette, a drawer dialog, the Copilot panel, in Light and Dark | No serious or critical violation |
| Keyboard: dialog | A drawer takes focus on opening, Tab never reaches the page behind it (the native modal dialog), Escape closes it and focus returns to the button that opened it | Pass |
| Keyboard: appearance choice | Space selects, arrow keys move between Light, Dark and System and apply at once | Pass |
| Keyboard: data grid | A sortable column header is reachable and operable with Enter and exposes `aria-sort` | Pass |
| Keyboard: shell | Skip link is the first tab stop and has a visible focus ring; banner, navigation and main landmarks present | Pass |
| Reduced motion (QG-27.9) | With `prefers-reduced-motion: reduce`, transition and animation durations are effectively zero and smooth scrolling is off | Pass |
| Reflow, 320 px wide (WCAG 1.4.10) | Every page, at 100% text: no horizontal scrolling | Pass after three fixes (below) |
| Text resize, 200% (WCAG 1.4.4) | Home, portfolios, goals, settings and net worth at 1280 px: no horizontal scrolling | Pass |
| Contrast | Design tokens are checked by `scripts/generate_tokens.py --check` (WCAG AA for text and the focus ring in both themes); axe checks the rendered pages | Pass |

## Findings and remediation

| Finding | Fix |
|---|---|
| Home (320 px): goal rows did not wrap, forcing a horizontal scroll | Goal rows wrap (`Dashboard.tsx`) |
| Portfolios (320 px): the card list used a fixed first column and long values pushed it wider than the screen | `minmax(0, 1fr)` column and word-breaking for values (`DataGrid.tsx`) |
| Card headers (320 px): action groups and the "As of" label could not shrink | Wrapping action group and shrinkable label (`cards.tsx`, `figures.tsx`) |

## Known limitation

At 320 px **and** 200% text size together (not a WCAG requirement, which treats reflow and text resize separately), the top bar's controls and some form rows still overflow by up to about 160 px (the Copilot page worst). Recorded for P14-T20 as a follow-up.

## Not done: manual screen-reader passes

The acceptance criteria call for manual NVDA (Windows) and VoiceOver (macOS and iOS) passes of the key journeys. They need a person with those tools and could not be done by automated testing. Until they are done the following are **not verified**: reading order and announcements of live regions (loading, errors, streamed Copilot answers), chart alternatives read aloud (each chart has a text summary and a table alternative, checked by the automated tests only for presence), and form error announcements.

**Key journeys to cover:** sign in with multi-factor; Home; add a transaction; Portfolio and holdings table; Analytics and chart table; Calculator; Goals (create, edit); Copilot question and answer; Reports download; Settings and appearance choice.

Record each pass here with the date, tester, tool and version, and what was found.

| Date | Tester | Tool and version | Journeys | Findings |
|---|---|---|---|---|
| — | — | NVDA | — | not yet done |
| — | — | VoiceOver (macOS, iOS) | — | not yet done |
