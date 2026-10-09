# WealthSphere — Detailed Project Brief (v1.1)

          WealthSphere

              AI-Powered Portfolio & Wealth Management Platform

 Detailed Project Brief
      Android + iOS Mobile Application | Portfolio Analytics | Compound Growth
                      Forecasting | AI Investment Intelligence




 Purpose: Define the product, architecture, functional modules, AI design, security model and phased
 implementation approach for a cloud-ready personal wealth intelligence application.





                          Version 1.0 - September 2026





WealthSphere - Detailed Project Brief                                                                                        Page 1

 1. Executive Summary
 WealthSphere is a mobile-first personal wealth intelligence platform for Android and iOS. It consolidates multiple
 investment vehicles into one portfolio view, measures performance, tracks passive income and net worth, models
 compound growth, manages financial goals, and uses an AI Investment Intelligence layer to help users research
 possible investment opportunities using current market evidence, portfolio context and transparent risk analysis.

 The product is designed to move beyond a basic portfolio tracker. Its long-term role is to become a personal wealth
 operating system: a trusted record of assets and transactions, a deterministic financial analytics engine, a
 scenario-planning platform, and an AI conversational interface for understanding wealth.
 Design principle: AI is not the source of financial truth. Portfolio facts come from authorized internal APIs;
 prices and research come from trusted data providers; calculations come from tested financial services; the
 LLM explains, compares and orchestrates these results.
 2. Product Objectives
  • Provide a unified view of investments across countries, currencies and asset classes.

  • Support Android and iOS from a shared Flutter codebase with native security capabilities.

  • Measure portfolio value, return, income, allocation, concentration and historical growth.

  • Provide compound-growth modelling for lump sums, recurring contributions, inflation and scenarios.

  • Allow users to define wealth goals and calculate contributions required to reach them.

  • Track assets and liabilities to calculate net worth.

  • Provide an AI Wealth Copilot for natural-language portfolio questions.

  • Provide AI Investment Intelligence that surfaces research opportunities using current evidence, user constraints
 and portfolio context.

  • Maintain security, privacy, auditability and explainability suitable for a financial application.

  • Remain extensible for broker/bank integrations, family wealth and adviser capabilities.
 3. Mobile Platforms and User Experience
 3.1 Android and iOS
 Android: Google Play distribution. iOS: Apple App Store distribution. Flutter is recommended to share most
 application code while supporting Face ID, Touch ID, Android biometrics, secure key storage, push notifications and
 deep links.
 3.2 Primary Navigation
 Home | Portfolio | AI Wealth | Goals | More

  • Home: total wealth, performance, allocation, passive income, goals and AI insight cards.

  • Portfolio: portfolios, holdings, transactions, asset detail, performance and allocation.

  • AI Wealth: chat, investment opportunities, Portfolio Doctor, research, comparison, simulator and watchlist.

  • Goals: target amount, progress, forecast and required contribution.

  • More: net worth, calculator, reports, alerts, documents, profile, security and settings.
 4. Supported Investment Vehicles




WealthSphere - Detailed Project Brief                                                                                        Page 2

  Asset Class             Examples                          Measurements

  Stocks                       Listed equities                                Price, value, P/L, dividends, return

  ETFs / Funds                Index, thematic, mutual                    NAV/price, distributions, return

  Bonds                     Government/corporate                   Coupon, maturity, yield, value

 MMF / Fixed Deposit       Cash-management                            Principal, yield, interest, maturity

  Real Estate / REITs          Property/listed property                      Valuation, rent, distributions, appreciation

  Crypto                  BTC, ETH, others                           Quantity, market value, P/L

  Pension / SACCO           Retirement/co-operative                     Contributions, value, income

  Private Business             Private ownership                           Valuation, ownership, distributions

  Cash / Commodities         Savings, gold, etc.                          Balance/quantity, value, return

  Custom Assets              User-defined                              Configurable valuation and income

 5. Core Functional Modules
 5.1 Identity & Security
 Registration, email verification, MFA, OAuth/OIDC, biometric unlock, profile, base currency, locale, risk profile,
 investment horizon, notifications and privacy settings.
 5.2 Portfolio Management
 Multiple portfolios, holdings, valuations, portfolio currency, historical value, notes and documents.
 5.3 Transactions
 Buy, sell, deposit, withdrawal, dividend, interest, coupon, rent, distribution, fee, tax, transfers and valuation
 adjustments. Preserve auditability.
 5.4 Multi-Currency
 Keep investments in native currencies while consolidating reports into the user's base currency using timestamped
 FX data.
 5.5 Portfolio Analytics
 Invested capital, market value, realized/unrealized P/L, return, CAGR, XIRR, time-weighted return, income yield,
  allocation, concentration, currency/geographic/sector exposure, drawdown and volatility.
 5.6 Compound Growth & Forecasting
  Initial capital, recurring contributions, contribution escalation, expected return, compounding, inflation, fees and time
 horizon.
 5.7 Financial Goals
 Target amount/date, progress, gap, required contribution, estimated completion and scenario comparison.
 5.8 Passive Income
 Dividends, interest, coupons, rent, REIT distributions, business distributions and other recurring investment income.
 5.9 Net Worth
 Assets less liabilities including property, investments, cash, businesses, mortgages and loans.



WealthSphere - Detailed Project Brief                                                                                        Page 3

 5.10 Market Data & Research
 Prices, FX, historical data, licensed research/news and macro indicators with provenance and timestamps.
 5.11 Watchlists & Alerts
 Price targets, maturity reminders, allocation thresholds, contribution reminders and goal milestones.
 6. Compound Growth and Forecasting Engine
 The calculator must be implemented as deterministic, independently tested financial code rather than an LLM
  calculation.

 Core lump-sum model: FV = PV x (1 + r)^n

  • Inputs include starting capital, recurring contribution, expected return, frequency, period, inflation, contribution
 growth and fees.

  • Support conservative, base and aggressive user-defined scenarios.

  • Return projected value, total contributed capital, projected growth, inflation-adjusted value and yearly chart series.

  • Solve for the periodic contribution required to reach a target.

  • Clearly identify assumptions; projected returns are not guaranteed.
 7. AI Wealth Copilot
 The AI Wealth Copilot provides a conversational interface to authorized portfolio data and deterministic tools. It can
 answer portfolio questions and invoke forecasting or analytics functions.
 Security boundary: the LLM receives no unrestricted database or SQL access. It can only call allow-listed
 internal tools that validate authorization and return structured results.
 8. AI Investment Intelligence
 This module identifies possible investment opportunities for research using current market evidence, user
 constraints and portfolio context. A controlled pipeline filters and scores the investment universe, checks suitability
 and diversification, retrieves evidence, and then uses the LLM to produce a structured explanation.
 8.1 Inputs
  • Risk profile, investment horizon, available capital and liquidity needs.

  • Existing allocation, concentration, currency and geographic exposure.

  • Financial goals.

  • Current prices and historical data.

  • Fundamental and valuation metrics where applicable.

  • Macroeconomic indicators and licensed research/news signals.

  • Data freshness and quality.
 8.2 Opportunity Output
  • Instrument and asset class.

  • Thesis and why it surfaced.

  • Supporting evidence and data-as-of timestamp.




WealthSphere - Detailed Project Brief                                                                                        Page 4

  • Risk level and key downside factors.

  • Portfolio and diversification impact.

  • Scenario assumptions and research horizon.

  • Transparent score explanation if scoring is used.

  • Evidence/source references and actions to Research, Compare or Simulate.
 Guardrail: opportunity scores are analytical aids, not promises of performance. The LLM must not invent
 market facts or expected returns.
 9. Portfolio Doctor
  Portfolio Doctor evaluates concentration, asset-class balance, sector/geographic/currency exposure, liquidity,
  volatility, income dependence and goal alignment. It produces observations and alternative scenarios rather than
 automatically executing trades.
 10. Technical Architecture
 Recommended stack: Flutter/Dart for Android and iOS; Python/FastAPI, Pydantic, SQLAlchemy, Alembic and
 PostgreSQL for backend services; Redis for caching; RabbitMQ/Celery for asynchronous work; Docker for
 local/production packaging; Keycloak for open-source identity; OpenAI through a dedicated AI orchestrator.

          Android / iOS (Flutter) | API Gateway | +------+-----------+-------------+ | | | Identity Portfolio
          Analytics | | | +------------ PostgreSQL --------+ | AI Orchestrator / \ Internal Tools Market/Research \ /
          OpenAI / LLM
 For the MVP, a modular monolith can reduce operational complexity while preserving service boundaries for later
  extraction.
 11. Core Data Model
  • users, user_profiles, risk_profiles

  • portfolios, portfolio_members

  • assets, asset_metadata, holdings

  • transactions, valuations, market_prices, fx_rates

  • income_events, liabilities

  • goals, goal_scenarios, forecast_scenarios

  • watchlists, watchlist_items, alerts

  • research_items

  • ai_conversations, ai_messages, ai_tool_calls

  • ai_recommendation_runs, ai_opportunities

  • audit_events, documents, notification_preferences

 Use UUID identifiers and PostgreSQL NUMERIC/DECIMAL for money and quantities where precision matters.
 Avoid binary floating-point for money.
 12. API and AI Tool Strategy
 Use versioned REST endpoints under /api/v1 with OpenAPI contracts generated by FastAPI. The backend remains
  authoritative for financial calculations.




WealthSphere - Detailed Project Brief                                                                                        Page 5

 Allow-listed AI tools should include portfolio summary, allocation, performance, net worth, goal progress, compound
 forecast, market snapshot, investment-universe search, asset research, asset comparison and portfolio risk
 analysis. Every tool must validate user authorization and log an auditable event.
 13. Security and Privacy Requirements
  • TLS 1.2+; prefer TLS 1.3; encryption at rest.

  • OAuth/OIDC with PKCE and MFA.

  • Secure mobile token storage and refresh-token rotation.

  • Server-side authorization on every resource; IDOR tests.

  • Rate limiting, brute-force protection and input validation.

  • Secrets in Vault/cloud secret manager, never source control.

  • Audit trails for financial changes and AI recommendation runs.

  • Backups, restore tests and disaster recovery.

  • SAST, dependency/container scanning and SBOM generation.

  • OWASP MASVS and OWASP API Security reviews.

  • Privacy, retention, export and account-deletion workflows.
 14. AI Quality and Explainability
  • AI is not the financial calculation engine or market-data source.

  • Only allow-listed tools access user data.

  • Validate LLM output with structured schemas.

  • Record model/provider/version and data timestamps.

  • Test prompt injection and cross-user data access.

  • Qualify stale or insufficient evidence.

  • Separate observed data from assumptions/scenarios.

  • No automatic trading in the initial release.

  • The user makes the final investment decision.
 15. Delivery Roadmap

  Phase                    Primary Deliverables

  0 - Foundation               Repository, Flutter shell, FastAPI, PostgreSQL, Redis, Keycloak, Docker, CI/CD, telemetry

  1 - Portfolio Core               Portfolios, assets, transactions, holdings, manual valuation, multi-currency dashboard

  2 - Analytics                Performance, allocation, income, net worth, calculator, goals

  3 - Market Data               Prices, FX, historical data, automatic valuation, watchlists

  4 - AI Copilot                AI orchestrator, portfolio tools, secure chat, Portfolio Doctor, audit trail

  5 - AI Intelligence            Opportunity screening, evidence, scoring, suitability, compare/simulate

  6 - Production                Security/load tests, backup/DR, monitoring, App Store and Google Play releases




WealthSphere - Detailed Project Brief                                                                                        Page 6

 16. MVP Acceptance Criteria
  • One codebase builds for Android and iOS.

  • Secure portfolios and supported investment/transaction recording.

  • Backend-authoritative portfolio totals and multi-currency views.

  • Deterministic compound and goal forecasts with automated tests.

  • Portfolio performance, allocation, income and net worth views.

  • Market data with provenance and freshness.

  • AI answers authorized portfolio questions only through controlled tools.

  • AI opportunities include rationale, risks, assumptions, timestamp and evidence.

  • Cross-user data access is prevented and tested.

  • CI/CD, logging, monitoring, backups and security scanning operate before production.
 17. Recommended Development Sequence
 Repository + CI -> Identity -> Database schema -> Portfolio/assets -> Transactions/holdings -> Multi-currency ->
 Dashboard -> Analytics -> Compound calculator -> Goals -> Net worth/income -> Market/FX integration -> AI tool
 layer -> AI Wealth Copilot -> Investment Intelligence -> Production hardening -> Android/iOS store release.

 The accompanying Markdown implementation guide is designed for direct use with Claude Code and contains
 repository structure, data model, API examples, AI tool contracts, security requirements, testing strategy and
 staged implementation prompts.





WealthSphere - Detailed Project Brief                                                                                        Page 7



---

# UI/UX Design Specification — Approved Product Direction (v1.1)

## Design intent
WealthSphere must deliver a premium, approachable fintech experience on **both Android and iOS**, combining digital-banking simplicity with professional portfolio analysis. The concept board is a **visual direction**, not a pixel-perfect specification or proof of working functionality. Figures, opportunities, scores, and charts in the mockups are illustrative sample data only.

### Brand tokens
| Token | Value | Use |
|---|---|---|
| `color.navy.900` | `#102A43` | Headers, dark backgrounds, primary text |
| `color.teal.600` | `#0D9488` | Positive actions, portfolio growth, success states |
| `color.gold.400` | `#F2B84B` | Premium accent, highlights, goal milestones |
| `color.blue.600` | `#2563EB` | Primary CTA and selected navigation |
| `color.surface.light` | `#FFFFFF` | Light cards and screens |
| `color.surface.subtle` | `#F5F7FA` | Light app background |
| `color.text.muted` | `#64748B` | Supporting text |
| `color.danger` | `#DC2626` | Loss and risk signals, always with text/icons |

Use semantic tokens rather than hard-coded widget colors. Provide dark-mode equivalents and WCAG-aware contrast. Typography: platform-appropriate sans serif, scalable with system text settings; 8-point spacing grid; rounded cards (12–20dp), 44pt iOS / 48dp Android minimum touch targets where feasible.

## Primary navigation
**Home | Portfolio | AI Wealth | Goals | More**. Keep tab selection stable; nested flows use standard back navigation. AI chat can also open contextually from asset, portfolio, forecast and goal screens.

## Screen inventory and required UX behavior
| # | Screen | Required UI elements and behavior |
|---|---|---|
| 1 | Welcome & Onboarding | Brand intro, value proposition, onboarding carousel, Get Started / Sign In, skip accessible where appropriate |
| 2 | Sign In / Sign Up | Email, password or configured identity flow, MFA, secure reset, biometrics for returning users, validation and error feedback |
| 3 | Home Dashboard | Total wealth, return and period selector, chart, portfolio/net worth/income/goal cards, AI insight summary, personalized reorderable widgets |
| 4 | Portfolio Overview | Portfolio selector, value, P/L, line chart, allocation donut and legend, performance metrics, drill-down to holdings |
| 5 | Investments / Holdings | Search, asset-class chips, sortable holdings, native currency and converted value, positive/negative change with accessible text |
| 6 | AI Wealth Copilot | Conversation thread, suggested questions, contextual portfolio scope, source/data timestamps, streaming/loading, refusal and retry states |
| 7 | Investment Details | Symbol/name, latest value, chart and period selector, fundamentals, income, holdings, transaction history, research, watchlist action |
| 8 | Transactions | Filter chips, grouped dated activity, amounts/fees/currencies, add transaction flow, confirmation, edit/correction audit trail |
| 9 | Compounding Calculator | Initial capital, recurring contribution, return assumption, horizon, contribution growth, inflation/fees advanced inputs, Calculate |
| 10 | Wealth Forecast | Conservative/base/growth selectable scenario cards, comparison chart, final value, contributions vs growth, nominal/real toggle, assumptions disclosure |
| 11 | Financial Goals | Goal cards, target and date, progress rings with numeric labels, on-track status, add/edit goal, required contribution |
| 12 | Portfolio Doctor | Health overview, concentration/currency/liquidity/volatility findings, severity + explanation, alternative scenario actions |
| 13 | AI Investment Opportunities | Research category chips, candidate cards, evidence, risk, data-as-of, explainable ranking, Compare/Research/Simulate actions |

## Shared Flutter component library
Build reusable and independently testable widgets: `WealthSummaryCard`, `MetricCard`, `PerformanceLineChart`, `AllocationDonutChart`, `PeriodSelector`, `PortfolioSwitcher`, `InvestmentRow`, `TransactionTile`, `ScenarioCard`, `ForecastComparisonChart`, `GoalProgressCard`, `PortfolioHealthCard`, `OpportunityCard`, `EvidenceSourceChip`, `RiskLabel`, `CurrencyAmount`, `EmptyState`, `ErrorState`, `SkeletonLoader`, `WealthBottomNav`, `AIChatComposer`, `DisclosurePanel`.

## Interaction rules
- Charts: period selection, accessible data summary, tooltips, loading/empty states, currency-aware formatting and date labels.
- Forecast: tap scenario to update chart and values; label assumptions prominently; show contributed capital separately from modeled returns.
- AI opportunity: `Research` opens evidence; `Compare` opens side-by-side analysis; `Simulate` pre-fills a scenario with clearly marked assumptions. No automatic trades.
- Dashboard: configurable card order and visibility, persistent per-user preferences.
- Contextual AI: portfolio/asset/goal context must be explicitly shown and authorized; users can change or remove context.
- Use skeleton loading, clear offline/stale-data banners, retry states and understandable validation errors.
- Support push-notification deep links, safe-area insets, iOS swipe/back conventions and Android system back navigation.
- Support light/dark themes, reduced motion, screen readers, dynamic text scaling, RTL-ready layout, localization and non-color-only indicators.
- Do not embed investment advice as fixed UI text; opportunity content must come from authorized, timestamped, evidence-backed services.

## Mobile responsiveness and testing
Support small and large Android phones and current iPhone sizes; tablets may use adaptive layouts in a later phase. Use Flutter breakpoints and avoid fixed pixel positioning. Verify portrait layouts, keyboards, notches, safe areas, long translated strings, large text, dark mode and accessibility. Add widget/golden tests for design-system components and integration tests for key journeys.

## UX delivery gates
1. Establish design tokens, themes, typography and navigation shell.
2. Implement high-fidelity Home, Portfolio, Calculator, Forecast and AI Wealth screens using mock data with an explicit `DEMO` indicator.
3. Add remaining eight screens and shared component states.
4. Connect backend APIs and replace mock data; ensure loading/error/offline states.
5. Complete accessibility and Android/iOS QA; compare implementation against the concept board.

## Visual reference
Reference concept board: `docs/design/wealthsphere-ui-concept.png` (copy the supplied design reference into the repository). The image is inspirational, not a strict source for copy, calculations, portfolio data, asset prices, or recommendations.

## Forex Trading Intelligence Module (proposed extension, 2026-10-09)
An optional workstream (plan phase P12, ADR-0009) adds AI-assisted forex market intelligence to WealthSphere as **decision support and paper trading only**: timestamped live quotes with feed status, technical analysis, probabilistic forecasts validated against baselines, an Opportunity Ranking Dashboard, a deterministic trade-risk calculator, backtesting, paper trading with a journal, and an AI Forex Copilot that uses allow-listed tools. It does not execute trades, does not promise returns, and keeps paper balances separate from real wealth. It starts only after the core platform phases P08-P13 and is gated by quality gates QG-13…QG-20. See SOLUTION_INTENT section 34 and docs/design/forex-technical-design.md.
