# FX provider licence review (P11-T12.1)

Date: 2026-10-13. Reviewer: Claude (engineering review of the published terms, **not legal advice**). Decision owner: the user (DEC-25). Sources read on 2026-10-13:

- ExchangeRate-API terms of use: https://www.exchangerate-api.com/terms
- ECB copyright and disclaimer: https://www.ecb.europa.eu/home/disclaimer/html/index.en.html
- ECB euro reference rates page: https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html

## What WealthSphere does with the rates

| Use | Where |
|---|---|
| The server fetches rates against USD, at most once per 15-minute window (about 2,976 requests a month) | `app/modules/fx/refresh.py`, [fx-refresh.md](design/fx-refresh.md) |
| The server stores them, including history, to value each user's own portfolio in their reporting currency | `fx_rates`, `fx_snapshots` |
| Signed-in users see rates, rate status, and converted values in the app; the AI assistant quotes them in answers | `/api/v1/fx/*` (every endpoint requires sign-in), the converter, the Home status line, the FX AI tools |
| No public or third-party access to the rates; no resale; no trading on the rates | — |

## ExchangeRate-API (primary, DEC-25)

| Term (quoted from their terms) | Our use | Assessment |
|---|---|---|
| A "non-transferable, non-exclusive, revocable and limited license" | One company account, used only by our backend | Fits |
| "both Free Plan and paid ExchangeRate-API accounts are suitable for either commercial or personal use" | Commercial app on the Pro plan | Fits |
| "this license does not permit re-distribution of our data"; data "may only be used for your end purposes" | Rates are shown to our own users as part of valuing their portfolios | Likely fits; **ask them to confirm** (below) |
| No use in "any product or service that offers programmatic or automatic access to exchange rate data" | Our API serves rates only to our own authenticated app; no public or partner API | Likely fits; **ask them to confirm** |
| "Users are given permission to store & re-use any data retrieved from our API"; "caching is for customer end-use only" | Stored rates and history serve only our users' own valuations | Fits |
| Attribution | No requirement stated | We name the source anyway (below) |
| Data "only suitable for informational or illustrative purposes"; using rates for transactions "explicitly not recommended"; no warranties; liability capped at ZAR 500 | The app never executes trades (CLAUDE.md); every conversion carries "Indicative rate for information; not a quote for a transaction", and the converter always shows "Exchange rates are for information only, not for transactions" | Fits; the warranty and liability limits are a business risk to accept |
| The Free Plan "can be discontinued … without notice"; paid fee changes need "at least 60 days" notice | Pro plan (paid) | Pro chosen for this reason |
| The terms can change, effective on next use or 30 days after posting | — | Re-check the terms before each release (P17) |
| South African law and courts | — | Business risk to accept |

**Open before production (not before P11-GATE):**

1. **Budget:** Pro plan, about USD 10 a month. Approved by the user on 2026-10-13. Confirm the price on their pricing page when buying.
2. **Written confirmation** from ExchangeRate-API that the use above is within their licence, including whether failed or "quota-reached" requests count toward the quota. Draft email (for the user to send):

   > Hello, we're building WealthSphere, a personal wealth app (Android and iOS). We'd like to confirm the following use under a Pro plan:
   > 1. Our server fetches rates (about 3,000 requests a month) and stores them, including history, to value each user's own portfolio in their chosen currency.
   > 2. Signed-in users see rates and converted values inside the app. Our backend serves rates only to our own authenticated app, never as a public or third-party API.
   > 3. Do failed requests, or requests answered with "quota-reached", count toward the monthly quota?
   >
   > Thank you.

3. The real-provider soak (P15-T11) checks quota counting and publication times against the live service.

## ECB euro reference rates (fallback)

| Term (quoted) | Our use | Assessment |
|---|---|---|
| Free use of information from the site; "when such information is distributed or reproduced, it must appear accurately and the ECB must be cited as the source" | Rates are stored and shown unchanged (exact decimals); crossed rates record their path | Fits now that the source is shown (below) |
| Modified information must be labelled as such | Rates crossed through EUR or USD show "Through AED → USD → EUR" | Fits |
| Information included in documents that are sold must state that it is free on the ECB website | Nothing is sold that contains ECB data | Not applicable; re-check if paid reports are introduced |
| "The reference rates are published for information purposes only"; using them for transactions "is strongly discouraged"; no liability for decisions | Same notices as above; no trading | Fits |
| Published around 16:00 CET on working days, "except on TARGET closing days" | Daily status windows (DEC-26); with ExchangeRate-API first, the ECB is only the fallback | Fits |

## Changes made in P11-T12 to meet the terms

- **Source shown wherever rates appear:** the FX status line (Home, the currency selector, the converter) and every conversion result say "Rates: European Central Bank" or "Rates: ExchangeRate-API", naming each source once. Widget tests in `test/features/currency/currency_test.dart`.
- **Information-only note** always visible on the converter, translated (ARB `converterInformationOnly`), in addition to the server's notice on each conversion.
- **Provider order:** ExchangeRate-API first, ECB as fallback (`fx_provider_order`). The weekend gap is gone and the request count stays the same (re-run soak in [fxcur-soak-report.md](fxcur-soak-report.md)).

## Conclusion

Based on the published terms, both licences permit the intended display and caching: rates for our own signed-in users, stored for their own valuations, sources named, shown as information only. Two items remain conditions for production, not for P11: the Pro plan purchase, and ExchangeRate-API's written confirmation.
