# Web portal: appearance (Light, Dark, System) design (P14, alias P14-UI-07 to P14-UI-10)

**Status:** Approved with the P14 plan change by the user on 2026-10-15. It assumes the proposed stack (Next.js with a Backend-for-Frontend, ADR-0018). If P14-T02 chooses Flutter Web, the preference, its storage and the behaviour below stay the same, and only §4 changes (Flutter `ThemeMode` plus a bootstrap in `index.html`).

## 1. Requirements

- Three explicit options: **Light**, **Dark** and **System**. System is the default.
- System follows `prefers-color-scheme` and reacts **while the page is open**. A system change never overwrites the user's saved choice.
- The choice persists across reloads. It is the same choice on every device and channel where the backend allows it.
- No flash of the wrong theme on the first paint. A change applies at once, without a reload.
- Every surface follows the theme: pages, charts, tables, dialogs, tooltips, menus, toasts and native form controls.
- The selector is reachable and usable by keyboard and screen reader in every mode.

## 2. What exists already

| Piece | State |
|---|---|
| Backend preference | `theme_mode: "system" \| "light" \| "dark" \| null` in `GET/PATCH /api/v1/me/preferences` (`app/modules/identity/schemas.py`); `null` means "system". **No backend change is needed** |
| Mobile | Light, Dark and System in Settings › Appearance (`ThemeModeController`). **Saved on the device only** (`ui.theme_mode`), not in `/me/preferences` |
| Tokens | Mobile `BrandPalette` and `WealthColors` hold the light and dark values, with measured contrast. P14-T03 moves them to `design/tokens/wealthsphere.tokens.json` and generates the Dart and CSS output |

## 3. Preference model

- **Stored value (the "preference"):** `system`, `light` or `dark`.
- **Resolved value (the "theme"):** `light` or `dark`. It equals the preference, or the browser's `prefers-color-scheme` when the preference is `system`.
- **Precedence when signed in:**
  1. the server value from `/me/preferences`;
  2. the `ws_theme` cookie;
  3. `system`.
- **Signed out** (sign-in and error pages): the cookie, otherwise `system`.
- **The `ws_theme` cookie:**
  - holds only the preference word;
  - `Path=/`, `SameSite=Lax`, `Secure`, valid for one year;
  - **not** HttpOnly, so the page can update it instantly;
  - no session data or token ever goes into it, or into any other browser storage (DEC-31);
  - any value other than the three words is treated as `system`.

## 4. Rendering without a flash

1. The server renders `<html data-theme-pref="{preference}">` from the cookie, or from the session's preferences at the sign-in callback. The BFF fetches `/me/preferences` once at sign-in and sets the cookie before the first page is rendered.
2. The generated CSS defines the tokens per resolved theme:

   ```css
   :root, [data-theme-pref="light"] { /* light tokens */ color-scheme: light; }
   [data-theme-pref="dark"]          { /* dark tokens */  color-scheme: dark; }
   @media (prefers-color-scheme: dark) {
     [data-theme-pref="system"]      { /* dark tokens */  color-scheme: dark; }
   }
   ```

   The **System mode resolves in CSS alone**, so the first paint is correct with or without JavaScript. Native controls and scrollbars follow `color-scheme`.
3. `<meta name="theme-color">` is emitted twice, once per `media` query, so the browser chrome matches too.
4. There is no theme transition animation, so nothing fades between themes or flashes on load.

## 5. Changing the theme

1. The selector sets `data-theme-pref` on `<html>` and writes the cookie. The page re-themes in the same frame.
2. When signed in, the client calls `PATCH /me/preferences {"theme_mode": …}` through the BFF, with the CSRF header.
   - If the call fails, the local choice stays and a non-blocking notice says "Saved on this browser only". The next change retries.
   - Cross-device updates arrive at the next sign-in or page load. There is no push in v1 (DEC-35).
3. A `BroadcastChannel("ws-theme")` message updates other open tabs at once.
4. A `matchMedia("(prefers-color-scheme: dark)")` listener updates only the **resolved** theme in a React context, which charts use (§6). It never writes the preference.

## 6. Theme-aware components

- **Tokens only.** Components use CSS variables (`--ws-surface`, `--ws-text`, `--ws-series-1..8`, …). A lint rule rejects colour literals in `web/src` outside the generated token files, mirroring the Flutter style guard.
- **Charts:** ECharts (portfolio, allocation, currency exposure, net worth, forecast and compounding) and Lightweight Charts (forex candles) take colours as values, per ADR-0018. A `useChartTheme()` hook reads the computed token values and redraws when the resolved theme changes. Small SVG pieces drawn by our own components, such as sparklines and the distribution bar, use CSS variables directly.
- **Axes, gridlines, legends and tooltips** have their own tokens (`--ws-chart-axis`, `--ws-chart-grid`, `--ws-tooltip-surface`). The dark tooltip card follows the reference (image 1) in both themes.
- **Gains and losses** always pair colour with a sign, an arrow and text (`ChangeIndicator`). Series are told apart by markers or patterns as well as hue.
- **Dialogs, menus, toasts and tooltips** render through portals inside `<html>`, so they inherit the theme; none sets its own colours.
- **Images and illustrations:** single-colour icons use `currentColor`. Any illustration has light and dark variants chosen by the resolved theme.

## 7. The selector

- **Settings › Appearance** (P14-T16) and the **profile menu** (P14-T06):
  - a radio group labelled "Appearance" with Light, Dark and System;
  - System's description reads "Follows your device (currently Dark)".
  - Arrow keys move between options and the choice applies on selection. The focus ring is visible in both themes.
- **Top bar** (P14-T06): a compact icon button that cycles Light → Dark → System. Its accessible name states the current and next mode ("Appearance: Dark. Switch to System"). Its tooltip says the same.
- The same words are used on mobile: Light, Dark, System.

## 8. Mobile alignment (proposal DEC-40)

The mobile app keeps its choice on the device only. For one preference across devices, P14-T18 (cross-platform synchronisation) would make the app read `theme_mode` from `/me/preferences` at sign-in and write it on change, keeping the device copy for offline start. This changes mobile behaviour, so it needs the user's approval.

## 9. Verification (QG-36)

| Check | How |
|---|---|
| Resolution logic | Unit tests: preference × system value → resolved theme; unknown cookie value → system |
| No flash | Playwright with JavaScript disabled: the first paint has the expected background for each preference × `colorScheme` (light, dark), checked by computed style and a screenshot |
| Live system change | Playwright `page.emulateMedia({ colorScheme })` while open: the resolved theme changes and the stored preference stays `system` |
| Persistence | Choose Dark, reload, then sign out and in again: Dark. Two tabs: the change propagates |
| Server sync | API contract test: the PATCH sends `theme_mode`; a failed PATCH keeps the local choice and shows the notice |
| Charts and overlays | Visual regression of the gallery and key screens in both themes; dialogs, tooltips and menus included |
| Contrast | Token generator test: every text and background pair ≥ 4.5:1 (≥ 3:1 for large text, UI parts and chart series) in both themes. axe-core in both themes |
| Keyboard and screen reader | Component tests for the radio group and the cycle button. NVDA read-through at the web UX gate |
| Reduced motion | No theme animation exists; other transitions are checked under `prefers-reduced-motion: reduce` |
