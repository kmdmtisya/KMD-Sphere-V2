# Forex Intelligence in the Android and iOS app, as built (P13-T11)

This document covers the forex section of the mobile app: where it lives, how it gets live prices, how each label stays visible, and how it is tested. The section shows the server's forex data and research, and the user's paper trading. The app computes no figure: every price, indicator, forecast, score, size, margin and P/L comes from the server (CLAUDE.md), or from the DEMO fixture in DEMO mode.

## 1. Where it is

**Entry point.** More → **Forex Intelligence**. The entry exists only when the section is available:
- **DEMO mode:** always, with every screen labelled DEMO.
- **Live mode:** only when the server has the forex module switched on. It answers 404 otherwise (DEC-23), and then the app shows no forex entry at all.

| Route | Screen | Shows |
|---|---|---|
| `/more/forex` | Home | The notice; the markets list; links to every forex screen; in-app notices; notification settings |
| `/more/forex/pair/:instrument` | Pair | The live price; the chart (15m, 1H, 4H, 1D); indicators; support and resistance; model forecasts; backtested rules; "Set up a trade" |
| `/more/forex/opportunities` | Opportunity Ranking and scanner | Research candidates filtered by timeframe, setup, risk level and liquidity tier, with every factor and risk |
| `/more/forex/risk` | Trade setup and risk calculator | The server's size, pip value, loss and profit after costs, risk/reward, margin, leverage, warnings and disclosures |
| `/more/forex/calendar` | Economic calendar | Events, with importance, actual and previous values, the consensus marked as an expectation, and DEMO events labelled |
| `/more/forex/paper` | Paper trading and journal | Account, positions (open and closed), new paper order, close at market, performance and journal |

**Copilot.** The "Ask the Copilot" link opens the AI tab. When an answer used the forex tools (P13-T10), the server-built sources (tool, time, data types, model version) appear as "Source" lines under the answer.

## 2. Labels that never disappear

- **Price type.** Every price shows its type: Simulated, Indicative, Delayed or Tradable quote. The tooltip says it is not an executable quote. Nothing is shown as a live executable price, and nothing trades.
- **Stale prices.** A stale or missing price shows "Stale" or "No price" in place of a number, so it never looks current.
- **PAPER TRADING.** The banner is on the paper screen, on the order form and on the order confirmation. Notices about closed paper positions are prefixed PAPER TRADING.
- **DEMO.** DEMO mode shows the DEMO badge. A calendar event the server marks as demo shows "DEMO event" even in live mode.
- **Forecasts.** Each forecast shows its probability label ("Calibrated" or "Requires calibration: not reliable"), its interval and model, and the server's notice.
- **Research candidates.** Each candidate is labelled "Research candidate", and the ranking's notice says it is not a recommendation.
- **Risk calculator.** Its result always ends with the server's disclosures, including that a stop can slip or gap.

## 3. Live prices (QG-19.2, QG-19.3, QG-19.5)

`ForexStreamClient` speaks the `WS /api/v1/forex/stream` protocol. The access token goes in the first frame and never in the URL.

| Situation | What the client does |
|---|---|
| Connected | On `ready` it subscribes to the pairs on screen |
| Connection dropped | Reconnects after 1, 2, 4, 8, 16, then 30 seconds, and subscribes again |
| No frame for 15 seconds (three missed heartbeats) | Treats it as a dropped connection |
| Close code 4401 (expired token) | Reconnects at once with a fresh token |
| Close code 4404 (forex switched off) | Stops |
| Close code 4429 (too many connections or messages) | Waits 30 seconds |
| App in the background, or device offline | `ForexStreamScope` pauses the stream: the socket closes and nothing retries |
| Back in the foreground or online | Reconnects at once |

**Responsive charts.** `LiveQuotesNotifier` applies stream updates at most every 250 ms, so a burst of ticks becomes one rebuild. The chart sits in a `RepaintBoundary`, so price updates elsewhere on the screen do not redraw it.

**DEMO mode.** `DemoForexStream` replays the fixture's simulated frames every two seconds.

## 4. Notifications (QG-19.4)

The server sends no forex push yet. The app produces in-app notices from data it already loads, and each kind can be switched off in Notification settings (kept on the device):
- a high-importance calendar event starting within the hour;
- a paper position closed in the last day.

The push deep-link allow-list now includes the forex home, the calendar and paper trading, so a future forex push can open them. URLs, other schemes and other paths are still refused.

## 5. Data

- `ForexRepository` has two versions: `LiveForexRepository` calls the forex API (P13-T02 to T09), and `DemoForexRepository` reads `assets/demo/forex.json`, made by `tool/generate_demo_fixtures.py`.
- The app chooses only time windows, meaning how much history to show. It chooses no price or result.
- In DEMO mode, paper trading is read-only: orders, closes and new accounts are refused with a message, and journal notes stay in memory.
- `JsonReader` gained `decimalsOrNull` (indicator series with warm-up gaps) and `keys`.

## 6. Tests

| Test | Covers |
|---|---|
| `test/features/forex/forex_stream_test.dart` | The token in the first frame and never in the URL; subscribe on ready and again after a reconnect; backoff; the silence watchdog; the close codes 4401, 4404 and 4429; pause and resume; a signed-out user; the DEMO replay |
| `test/features/forex/forex_data_test.dart` | Every fixture section parses; DEMO paper trading is read-only; the live repository's paths, queries and parsing; notices and their settings; forex deep links; the Copilot's source lines; stream updates batched into at most two rebuilds for 50 ticks |
| `test/features/forex/forex_screens_test.dart` | Each screen in DEMO mode, with the labels above; the calculator's validation and result; the scanner's filters; every screen at 2.0× text, in RTL and in dark mode with no layout error; the More entry present in DEMO and absent when the server answers 404 |
| `test/guards` | The DEMO-badge guard covers the forex screens (the calendar uses a per-event label) |

## 7. Limits

- **Manual device pass.** The plan asks for one on an Android and an iOS device; it is pending and recorded at P13-T12. CI builds Android (debug) and compiles iOS without signing.
- **Notifications are in-app only** until the server sends forex pushes.
- **Simulated data.** All forex data is simulated or DEMO until DEC-19 and DEC-20 are decided.
