# Web portal: supported browsers and browser-specific defects (P14-T20, QG-32.6)

## Supported versions

Approved by the user on 2026-10-16 (DEC-36, `P14_DECISIONS_2026-10-16.md`):

| Browser | Supported |
|---|---|
| Chrome | the latest two major versions |
| Edge | the latest two major versions |
| Firefox | the latest two major versions |
| Safari (macOS and iOS) | 17 or later |

Sign-in uses `__Host-` Secure session cookies, so deployments must serve the portal over HTTPS. Loopback HTTP is treated as secure by Chromium and Firefox, which is why the test servers work there.

## What is tested, and where

| Browser | Tested with | Journeys |
|---|---|---|
| Chrome (Playwright Chromium, or installed Chrome 155) | Every end-to-end spec, locally and in CI | All |
| Edge 155 (local) | `browsers.spec.ts` | Five widths (1440, 1280, 1024, 768, 375 px), Light and Dark, main interactions |
| Firefox (CI, Playwright's build) | `browsers.spec.ts`, and from this change the forex workspace journeys (`forex-workspace.spec.ts`, `forex-live.spec.ts`) with the forex module on | The same widths and themes; paper trading, notices, candle chart, streaming responsiveness, no real-money order |
| Safari / WebKit | Not tested | See below |

## Browser-specific defects

| Browser | Finding | Status |
|---|---|---|
| WebKit | Cannot sign in over the plain-HTTP test server: it will not store `__Host-` Secure cookies, as Safari would not. This is a property of the test setup, not a defect of the portal. | Not a defect. WebKit is not in CI; it needs an HTTPS test deployment (staging, P15). |
| Chrome, Edge, Firefox | No browser-specific defect was found in the journeys above. Differences met during the work (animation timing before accessibility scans, 320 px reflow, layout shift while loading) reproduced in Chromium too and were fixed for every browser. | None open. |

## Not covered

- Real Safari on macOS and iOS (QG-32.4), and so the WebKit run of the paper-trading journey (QG-33.9). Both wait for an HTTPS staging site and are recorded as open, not passed.
- Older versions than "latest two", mobile browsers on phones, and assistive technology combinations (see `WEB_ACCESSIBILITY_REPORT.md`).
