# Live repositories and the data-source switch (P09-T01)

The app reads either bundled DEMO fixtures or the WealthSphere API. Screens never know which.

- **Mode:** `DataSourceMode { demo, live }`, started from `--dart-define=WS_DATA_SOURCE=demo|live` (default `demo`; anything else fails at start). Every repository provider chooses its implementation from `dataSourceModeProvider`, so switching mode needs no screen change. A live repository that is not wired yet throws `UnsupportedError` (`liveNotWired`) instead of showing demo data as if it were real. T09 adds the release policy.
- **Client:** `buildApiClient` (Dio): bearer token with refresh and one retry, `X-Correlation-ID`, short timeouts, no logging interceptor.
- **Base class:** `LiveRepository` (`lib/core/network/live_repository.dart`): `getObject`, `getList`, `send` (with `Idempotency-Key` for writes) and `sendEmpty`. All parsing goes through the strict `JsonReader` (ADR-0013); a body of the wrong shape becomes `ApiErrorKind.invalidResponse` naming the field path, never a value. Live repositories return what the server says and never recalculate money.
- **Errors:** every failure is an `ApiException` (network, unauthenticated, forbidden, notFound, validation, rateLimited, server, invalidResponse, unexpected). `loadFailureOf` groups them into `LoadFailure` (offline, signedOut, forbidden, notFound, busy, unknown) and `LoadErrorView` words each one: offline, session ended (no Retry), refused (no Retry), missing, busy, generic. It shows the API support reference when there is one, never exception text. `AsyncValueView` uses it by default, so existing screens get the right state with no change.
- **DTOs:** hand-written on `JsonReader`, checked against the API by `docs/contracts/dto-mapping.json` (ADR-0013). The unused Freezed, json_serializable and build_runner dependencies were removed here, as that ADR planned.

## Home and Portfolio (P09-T02)

`LiveDashboardRepository` and `LivePortfolioRepository` read the API; `SyncedDashboardLayoutRepository` keeps the Home layout on the device and in the account (`PATCH /me/preferences`; the account wins on load, the device copy is used offline).

| Screen data | Endpoint |
|---|---|
| Greeting | `GET /me` (display name, else the email's local part) |
| Net worth, income, goals | `GET /net-worth`, `/income/summary`, `/goals/summary` |
| Portfolio list, name | `GET /portfolios`, `/portfolios/{id}` |
| Summary | `/portfolios/{id}/summary` + `/performance` (profit and return); `/portfolios/consolidated/summary` for all portfolios |
| Chart | `/portfolios/{id}/risk` points (incomplete points left out) |
| Allocation | `/portfolios/{id}/allocation`, asset-class slices named from `/asset-classes` |
| Metrics | return from `/performance`; annualised return and volatility from `/risk`; yield from `/income` |
| Holdings | `/portfolios/{id}/holdings` |

Rules kept: no figure is added, converted or derived in the app. A missing figure is null and shown as "Not available" or "No value yet"; an unpriced position sorts last and is never shown as zero; `DataQualityNotice` says when a total is incomplete or uses stale prices; Home shows no AI insight until the AI service exists (P10-T06).

**Known gap (follow-up):** the API has a consolidated *summary* only. For "All portfolios" there is no profit and loss, return, chart series, allocation or metrics, so those are empty or "Not available" rather than summed on the device. All-portfolio holdings are the per-portfolio lists joined (a position held in two portfolios appears twice). A backend consolidated performance, allocation and risk endpoint would close it. The "Unclassified" allocation label and the greeting fallback "there" are English literals in the repository layer.
