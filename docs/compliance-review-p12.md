# P12 disclosure and compliance review pack (P12-T10, DEC-10)

**Reviewer:** Kelvin Mutisya David. **Prepared by:** Claude (engineering draft, 2026-10-13). **Status: wording signed off as drafted on 2026-10-13. Nothing here is legal advice, and the jurisdiction questions remain open (section 4).**

**What you are asked to do:**
1. Mark each statement in section 1 as *approve*, *change* (with replacement wording) or *remove*.
2. Answer the jurisdiction questions in section 3.
3. Sign the table in section 5.

I then apply your changes (P12-T10.3), re-run the tests that pin this wording, and complete the task.

Scope: the AI Investment Intelligence features of P12 (Portfolio Doctor, investment universe and eligibility, scores, compatibility, research, opportunities, Compare, Simulate) in the API responses and the mobile app. P10/P11 wording, such as the assistant footer, is listed only where P12 screens reuse it.

## 1. Copy inventory (P12-T10.1)

All statements are English only today. The notices come from the server with every response; the mobile strings are in `lib/l10n/app_en.arb`.

| # | Where the user sees it | Wording | Source |
|---|---|---|---|
| 1 | Portfolio Doctor, every response | Observations from your own data against stated thresholds. Not investment advice. Scenarios are hypothetical: nothing is bought or sold. | `doctor/schemas.py` NOTICE |
| 2 | Doctor scenarios | Hypothetical: the share is lowered to the cap and the difference is spread over the rest of the portfolio in proportion to its current shares. Prices, fees and taxes are ignored. Not a recommendation and not an order. | `doctor/rules.py` SCENARIO_ASSUMPTION |
| 3 | Doctor liquidity finding | Liquidity is assumed from the asset class: cash and money market funds immediate; listed and pooled assets within days; fixed deposits, SACCO and pension holdings locked until maturity or notice; property and private holdings illiquid; custom assets unknown. | `assets/liquidity.py` |
| 4 | Doctor goals finding | Goal status is an estimate under each goal's own assumptions, not a certainty. | `doctor/rules.py` GOAL_NOTICE |
| 5 | Doctor screen footer | The Portfolio Doctor only describes and illustrates. It never places trades. | `doctorNoTrades` |
| 6 | Investment universe, every response | Eligibility only filters what analysis may consider; an eligible instrument is not a recommendation. DEMO instruments are fictional. | `universe/schemas.py` NOTICE |
| 7 | Jurisdiction outcome | Jurisdiction rules have not been legally reviewed yet; availability comes from the instrument source. | `universe/eligibility.py` JURISDICTION_NOTICE |
| 8 | Scores | Scores describe measured characteristics: past prices, costs, liquidity and risk class. They are not forecasts or expected returns, and not recommendations. | `scoring/scoring.py` NOTICE |
| 9 | Compatibility check | Hypothetical: the amount is added as new money and nothing is sold. Prices, fees and taxes are ignored. Not a recommendation and not an order. | `compatibility/impact.py` ASSUMPTION |
| 10 | Research, every response | Research is information, not advice. DEMO items are fictional. Check each item's source, licence status and date. | `research/api.py` NOTICE |
| 11 | Opportunities, every response | Research candidates selected by deterministic rules from your eligibility, measured characteristics, portfolio fit and retrieved evidence. Not advice and not a recommendation to buy or sell; no return is expected or promised. DEMO instruments are fictional. Actions: Research, Compare, Simulate. | `opportunities/schemas.py` NOTICE |
| 12 | Opportunities screen | For research only. Not advice, and returns are never guaranteed. | `opportunityNotAdvice` |
| 13 | Opportunities screen footer | WealthSphere never places trades. These ideas are for research only. | `oppNoTrades` |
| 14 | Compare, every response | Past figures describe what happened, not what will happen. No future return is shown. Not advice; DEMO instruments are fictional. | `compare/api.py` COMPARE_NOTICE |
| 15 | Compare screen | Side-by-side facts from the evidence on file. This is not a ranking or advice. | `oppCompareNote` |
| 16 | Simulate, every response | An illustration under the return assumptions you entered, not a forecast of this instrument. Real returns vary and can be negative; nothing is guaranteed. | `compare/api.py` SIMULATE_NOTICE |
| 17 | Simulate hand-off to the calculator | Enter your own return assumptions. WealthSphere does not predict this investment's returns. | `oppSimulateOwnReturns` |
| 18 | Instrument screens (P08/P12) | Informational only. WealthSphere does not place trades. | `investNoTrading` |
| 19 | Research notes (P08/P12) | Research notes are informational. They do not predict returns and are not advice. | `investResearchNote` |
| 20 | AI assistant footer, reused | Informational only, not financial advice. No trades are executed. | `aiFooter` |
| 21 | Every DEMO screen and item | DEMO badge; "(DEMO)" in instrument names; DEMO research notes. | `demoBadge` |
| 22 | AI-written explanations | Written by the model from the stored facts only; refused if they add a figure, forecast, guarantee, link or instruction; otherwise replaced by fixed wording. The app labels which one it is (`explanation_source`: model or template). | `opportunities/explain.py` |

**Wording the system refuses to produce (tested):** guarantees, certainty, expected or projected returns, target prices, "buy" or "sell" instructions, links, invented figures.

## 2. Observations from the engineering side

For you to accept or reject:

1. **"Not advice" is stated, but the app never says what WealthSphere is not.** The notices do not mention that WealthSphere is not a licensed investment adviser, broker or dealer. Whether that statement is needed, and in what form, is your call.
2. **Statements 12 and 16 use "guaranteed" in a denial.** The guard accepts negated uses ("not guaranteed"). Confirm you are comfortable with the word appearing at all.
3. **No statement covers risk of loss in general** on the opportunity screen. Item 14 says past figures do not predict the future, and item 16 says returns can be negative. Item 11 does not mention loss. Consider a standard "you can lose money" line.
4. **No statement about data sources and delays.** Item 10 says to check source, licence and date. Prices in the app can be up to 4 days old for listed instruments (the freshness rule). The app shows the date, but not a sentence saying prices may be delayed.
5. **Doctor severity words** (high, medium, low) describe how far a measure is beyond a threshold we chose. They are not a rating of the portfolio's quality or an investment risk rating. No on-screen sentence says so. Thresholds: `docs/design/portfolio-doctor.md` section 3.
6. **The eligibility rules include a "risk tolerance" ceiling** (conservative up to level 2, balanced 3, growth 4, aggressive 5). If this counts as a suitability assessment in either jurisdiction, different rules may apply. See question 3.5.
7. **Instruments, research and notices are DEMO.** No real security is shown to anyone. Production use depends on licensed data (DEC-04) and a second review of this copy when real instruments are introduced.
8. **Language:** English only. Swahili or Arabic disclosures would need translation and the same sign-off.

## 3. Jurisdiction questions (Kenya and the UAE)

Launch jurisdictions were set by the user for P12. The jurisdiction rules in code say only: the user's country of residence must be Kenya or the UAE, and the instrument must list that country as available. **No rule is based on a legal review.** I have not stated any regulator's requirements here, because I cannot verify them.

| # | Question for you |
|---|---|
| 3.1 | Does presenting scored, ranked research candidates to retail users require a licence or registration in Kenya (for example with the Capital Markets Authority) or in the UAE (Securities and Commodities Authority, or the free-zone regulators DFSA and FSRA)? If so, which, and under what conditions? |
| 3.2 | Do the notices in section 1 satisfy any mandatory risk warning or disclaimer for each country? If not, give the required wording. |
| 3.3 | Are any asset classes restricted for retail investors or for residents (for example cryptocurrency, private equity, property shares)? Each restriction can be added as an excluded class for that country (`JurisdictionRules.excluded_classes`). |
| 3.4 | Is residence the right test, or does citizenship or the user's account country matter? |
| 3.5 | Does the risk-tolerance filter amount to a suitability assessment or "know your customer" step, and what does that trigger? |
| 3.6 | Data protection: the model sees only candidate facts (no identity, no amounts). Does sending even that to an external model provider need a disclosure to the user in either country (see ADR-0017)? Account deletion and retention are in P15-T05. |
| 3.7 | Do you want the same wording in both countries, or a per-country disclosure shown by residence? The app already stores residence, so per-country text is possible. |

## 4. Reviewer's decisions (P12-T10.2)

*To be completed by the reviewer.* Use one line per item; leave blank to mean "not yet reviewed".

| Item | Decision (approve / change / remove) | Replacement wording or note |
|---|---|---|
| 1 to 22 | **Approve, unchanged** | Signed off as drafted. |
| Observations 2.1 to 2.8 | **No change to the wording** | Carried as open follow-ups for the first release with real instruments (the copy is reviewed again then, see item 7 of section 2): a statement that WealthSphere is not a licensed adviser or broker, a general loss-of-money line on the opportunity screen, a data-delay sentence, a note that Doctor severity is not a rating, and Swahili and Arabic translations. |
| Questions 3.1 to 3.7 | **Not answered; open** | No legal review has been done, so no jurisdiction is marked as reviewed. They must be answered before real instruments or live data are introduced, and before launch (P15-T05). |

## 5. Sign-off (acceptance: the reviewer signs off wording and jurisdictional disclosures)

| Role | Name | Date | Decision |
|---|---|---|---|
| Reviewer | Kelvin Mutisya David | 2026-10-13 | **Wording approved as drafted** (recorded on the user's instruction in the session) |

As signed: the jurisdiction notice (item 7) stays on every response, and jurisdiction outcomes stay marked `legally_reviewed: false`, because the jurisdiction questions are unanswered. Only DEMO instruments exist, so no real security is shown under this copy.

## 6. What changes when you sign (P12-T10.3)

- (Nothing needed changing: the wording was approved as drafted.) Had any been changed, statements would be updated in the backend and `app_en.arb`. The tests that pin the wording are updated with them.
- Any new excluded asset classes or per-country disclosures you specify are added as settings.
- `legally_reviewed` becomes true for a country only if you say its rules have been reviewed.
- This file is updated with the final approved copy and becomes the checklist for future copy changes.
