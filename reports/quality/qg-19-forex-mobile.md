# QG-19 (QG-FX-07): Mobile Experience — P13-T12, 2026-10-14

The method is in [docs/design/forex-mobile.md](../../docs/design/forex-mobile.md).

| Criterion | Evidence | Result |
|---|---|---|
| 19.1 Android and iOS builds pass | CI on PR #164 (run 38606515408): `android debug build` passed, `ios compile (no codesign)` passed, and `format, analyze, test (incl. goldens)` passed | Pass |
| 19.2 Charts remain responsive during streaming updates | `LiveQuotesNotifier` applies stream updates at most every 250 ms: `forex_data_test.dart::stream updates are batched into one state change per flush` (50 ticks give at most two rebuilds). The chart sits in a `RepaintBoundary`. The pair and home screens are tested with the stream on | Pass, with a limit: not profiled on a device (frame times); see the manual pass below |
| 19.3 Background and foreground transitions are handled | `ForexStreamScope` pauses the stream when the app is hidden and resumes on return; `forex_stream_test.dart::pause closes and stops retrying; resume reconnects at once`; the DEMO stream pauses too | Pass |
| 19.4 Notifications are tested | In-app notices for an upcoming high-importance event and a closed paper position, each respecting its setting; the settings round-trip and tolerate corrupt values; forex deep links are allowed, while URLs and other paths are refused (`forex_data_test.dart`: notices and deep links). The settings toggles work (`forex_screens_test.dart`) | Pass, with a limit: the server sends no forex push yet, so the tests cover in-app notices and deep-link routing |
| 19.5 Network interruption recovery is verified | `forex_stream_test.dart`: a dropped connection reconnects with backoff of 1, 2, 4 ... 30 s and subscribes again; 15 s of silence is a drop; 4401 reconnects with a fresh token; 4404 stops; 4429 waits longest. `ForexStreamScope` pauses offline and resumes when back online (connectivity provider) | Pass |

**Manual device pass: not done.** The plan's verification lists one. It has not been done on a physical Android or iOS device, and this report does not claim it. Everything above is automated: widget, unit and journey tests, the screens at 2.0× text, RTL and dark mode, and the CI builds. The device pass should be done before the forex section is released. It is a release item under P13-T14 and P17.

Run, 2026-10-14: `cd mobile/wealthsphere_app && flutter test test/features/forex test/journeys/forex_journey_test.dart test/guards`: 73 passed. The full suite passed on PR #164.
