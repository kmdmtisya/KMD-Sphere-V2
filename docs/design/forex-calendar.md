# Forex economic calendar, as built (P13-T04)

How P13-T04 was built: the calendar's event model, its sources, the event-risk windows, central-bank policy rates and their differential, and the API. The design is [forex-technical-design.md](forex-technical-design.md) section 6.

**Status: DEMO only (DEC-19).** No licensed calendar provider is wired up. The only data comes from a synthetic DEMO calendar; every DEMO name starts with "DEMO", and every value is fictional.

## 1. Three kinds of content, kept apart

| Kind | Fields | Meaning |
|---|---|---|
| Confirmed | `confirmed.actual` (once `released`), `confirmed.previous`, `confirmed.unit` | Published figures, as the source gave them |
| Expectation | `expectation.forecast` | The consensus forecast: an expectation, not a fact |
| Commentary | `commentary.text`, always with the label "Commentary from the source: not confirmed data" | Speculative text from the source. Never data |

They are separate columns in `forex_economic_events` (migration 0021), separate objects in the API, and need separate labels in the UI.

Every event also carries:
- its source, source URL and licence status, and whether it is DEMO;
- `retrieved_at`;
- `actual_seen_at`: when the actual value was first seen.

## 2. Ingestion and sources

- **Upsert and keep.** `calendar/ingest.py` upserts events by (source, source event ID). A scheduled release gains its `actual` when it is published. A published `actual` is never cleared by a later run that lacks it.
- **Policy rates** are upserted by (source, currency, effective date).
- **`DemoCalendarSource`** (`demo_calendar.json`) holds 11 synthetic templates: US, euro area, UK, Japan, Kenya and South Africa releases, Fed and ECB decisions, and a speech.
  - Schedules are set in local time with the IANA zone, so daylight saving and releases whose UTC date differs from their local date are exercised.
  - Values are deterministic. `actual` exists only once the release time has passed, and `previous` is the prior release's actual.
  - Ten policy rates appear once effective.
- **`IcsCalendarSource`** reads release schedules from an iCalendar (RFC 5545) feed, the format many statistics offices and central banks publish. It handles line folding, escapes, `TZID` and UTC times, and `CATEGORIES` as the importance.
  - A date with no time (all-day) is skipped and counted: it is not a release time.
  - A time with no zone is refused: it cannot be placed.
  - It is tested on a synthetic fixture; nothing is fetched.
- **Worker job** `forex_calendar_ingest` runs every hour at :10 when forex is switched on, covering a week back and 30 days ahead, idempotent per hour.

## 3. Time zones

- **Storage:** release times are stored in UTC.
- **API:** `scheduled_at` is in UTC; `scheduled_local` is the same instant in the user's profile time zone, or in `tz` when given (an IANA name, validated).

## 4. Event-risk windows

`calendar/risk.py` is pure functions:

| Importance | Window around the release |
|---|---|
| High | 30 minutes before to 60 minutes after |
| Medium | 15 minutes before to 30 minutes after |
| Low | No window |

- **Matching:** windows are half-open, and match a pair when they touch either of its currencies.
- **Who uses them:** the scanner and the risk engine (P13-T06, P13-T07), to raise the macro-event component and to warn on setups.
- **What a window is:** a schedule fact, not a prediction that the price will move.

## 5. API

These endpoints need sign-in and the forex flag (404 when it is off). They serve reference data, the same for every user.

- `GET /api/v1/forex/calendar?start&end[&currency…][&min_importance][&tz]`: the range is at most 92 days.
- `GET /api/v1/forex/calendar/risk?instrument[&at]`: returns the open windows for the pair at `at`, or now.
- `GET /api/v1/forex/policy-rates/differential?instrument`: returns each currency's latest effective rate with its bank, dates and source, and base minus quote in percentage points. When either rate is unknown the differential is `null`, never a guess.

The differential route was added to the market-data licence gate's reviewed list (docs/security.md): it serves DEMO rates only.

## 6. Tests

| File | What it covers |
|---|---|
| `tests/forex/test_calendar_core.py` | Validation, schedule rules, the DEMO source across daylight saving, the iCalendar adapter on the fixture, risk windows |
| `tests/forex/test_calendar_api.py` | Idempotent ingestion, a release gaining (and keeping) its actual, the content separation, UTC and local times, filters, risk windows, differentials, validation, the flag |
| `tests/forex/test_worker_jobs.py` | The hourly job: off when forex is off, and idempotent per hour |

## 7. Open items

- **A real calendar provider** needs DEC-19: a vendor, with licence terms for display and storage.
- **Rate differentials with a forward-looking component** (expected policy paths) are out of scope. Only published rates are shown.
- **Geopolitical items** are not ingested. They enter only as source-attributed items with timestamps (design section 6), when a source is approved.
