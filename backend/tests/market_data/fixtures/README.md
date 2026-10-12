# Contract fixtures

| File | Origin |
|---|---|
| `ecb_daily.xml` | **Recorded** from the ECB on 2026-10-12 (https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml). |
| `ecb_hist_recent.xml` | **Recorded** from the ECB's 90-day history on 2026-10-12, trimmed to the 6 latest days. |
| `exchangerate_api_*` | **Synthetic** (P11-T03, fixture-only approval): written in the response shapes of the public v6 documentation (standard, pair, historical requests and the documented `error-type` values) on 2026-10-12, with invented rates. No key exists and no live call was made. Re-record once a key and the licence are confirmed (P11-T12). |
| `coingecko_*`, `twelvedata_*` | **Synthetic**: written in the response shapes of the vendors' public API reference with invented values, because no API key exists yet. Re-record them from the real APIs once keys are available (P08-T09 tracks this) and keep the contract tests unchanged. |

No fixture contains a key or any personal data.
