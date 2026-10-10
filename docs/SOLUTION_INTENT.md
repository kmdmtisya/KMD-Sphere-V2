# WealthSphere - Solution Intent

## 1. Solution Name
**WealthSphere - AI-Powered Portfolio & Wealth Intelligence Platform**

**Tagline:** Track. Measure. Forecast. Grow.

## 2. Solution Intent
WealthSphere is intended to be a secure, scalable, mobile-first wealth and investment management platform that enables individuals to consolidate, monitor, analyse and forecast their wealth across multiple investment vehicles.

The solution will initially provide mobile applications for **Android and iOS**, supported by a cloud-based API, financial analytics engine, market-data integration layer and AI-powered investment intelligence platform.

The application should not operate merely as an investment tracker. Its long-term purpose is to become a **Personal Wealth Intelligence Platform** combining portfolio management, investment performance measurement, net-worth management, passive-income tracking, financial goal planning, compound-growth forecasting, market intelligence, investment research, AI-assisted portfolio analysis, AI-assisted opportunity discovery and wealth scenario modelling.

The system should help users answer:
- What do I own?
- What is it worth?
- How is it performing?
- Where is my wealth concentrated?
- What income is my wealth generating?
- What could my portfolio become in the future?
- What investment opportunities may be worth researching now?
- How would a potential investment affect my portfolio and long-term goals?

The system provides information, analysis and scenarios while leaving the final investment decision with the user.

## 3. Product Vision
WealthSphere should become the user's central source of truth for personal investments and long-term wealth creation.

```text
Portfolio Management -> Wealth Planning -> Investment Intelligence
        \                    |                    /
                     AI Wealth Copilot
                            |
                 Better-Informed Decisions
```

## 4. Target Platforms
- **Android:** production application distributed through Google Play.
- **iOS:** production application distributed through the Apple App Store.
- **Future Web:** consume the same backend APIs without redesigning core business services.

Flutter is the preferred mobile technology so Android and iOS share a common codebase while retaining native security capabilities.

## 5. Core User Journey
```text
Create Account
-> Secure Account
-> Create Portfolio
-> Add Investments
-> Record Transactions
-> Connect Market Data
-> Calculate Current Value
-> Measure Performance
-> Analyse Portfolio
-> Create Financial Goals
-> Forecast Future Wealth
-> Discover Investment Opportunities
-> Compare Alternatives
-> Simulate Portfolio Impact
-> User Makes Investment Decision
-> Continue Monitoring Wealth
```

## 6. Investment Universe
Initial investment types:
- Stocks
- ETFs
- Mutual funds
- Bonds and treasury instruments
- Money-market funds
- Fixed deposits
- REITs
- Real estate
- Cryptocurrency
- Commodities
- Cash and savings
- Pension investments
- SACCO/co-operative investments
- Private businesses/private equity
- Alternative investments
- Custom user-defined investments

The architecture must remain extensible so new investment types can be introduced without redesigning the portfolio engine.

## 7. Portfolio Management Intent
Users can maintain multiple portfolios such as UAE Investments, Kenya Investments, Global Investments, Property, Digital Assets, Retirement and Private Businesses. WealthSphere provides individual portfolio analysis and a consolidated wealth position.

## 8. Multi-Currency Intent
Each investment retains its native currency. The user selects a reporting/base currency. WealthSphere converts portfolio values using appropriate FX data while preserving original transaction currency and historical exchange-rate information.

_Extension (proposed 2026-10-10, ADR-0010, plan phase P11 FXCUR):_ the reporting currency is a **global user setting**, synced across devices and reachable from Settings and from Total Wealth on Home. Switching it changes only how figures are presented, everywhere in the app (dashboard, portfolios, holdings, analytics, net worth, income, goals, calculator, forecasts, AI, reports); it never changes balances, transaction amounts, transaction rates, portfolio base currencies, goal target currencies or forecast assumptions. Conversions use timestamped provider rates labelled current, cached or unavailable (never invented), one consistent rate snapshot per view, historical rates for past figures, and exact decimal arithmetic on the backend. A currency converter and authorised AI currency tools are included.

## 9. Portfolio Analytics Intent
Progressively support:
- Current market value and invested capital
- Profit/loss
- Realized and unrealized gains
- Percentage return
- CAGR
- XIRR / money-weighted return
- Time-weighted return
- Dividend, interest and rental income
- Portfolio yield
- Asset, geographic, currency and sector allocation
- Concentration
- Volatility and drawdown
- Historical performance
- Benchmark comparison

Financial calculations must be deterministic, tested application services and must not depend on an LLM.

## 10. Compound Growth Intent
Support initial capital, recurring investment, expected return, contribution growth, investment period, inflation and fees.

Provide conservative/base/growth scenarios based on user-selected or clearly sourced assumptions. Clearly separate contributed capital from projected investment growth. Forecasts must never be represented as guaranteed returns.

## 11. Goal-Based Wealth Management
Support goals such as portfolio/net-worth targets, retirement, education, property purchase, business capital, financial independence and passive-income targets.

Calculate current progress, target gap, required contributions and projected goal achievement based on explicit assumptions.

## 12. Net-Worth Intent
Net Worth = Total Assets - Total Liabilities.

Assets may include investments, property, businesses and cash. Liabilities may include mortgages, loans and other debts.

## 13. Passive-Income Intent
Track dividends, interest, bond coupons, rental income, REIT distributions, business distributions, staking/yield and other investment income.

## 14. AI Wealth Copilot
Users should be able to ask natural-language questions about their own authorized portfolio, net worth, performance, exposures, income and goal forecasts.

The AI must obtain answers through authorized application tools and must never receive unrestricted production database access.

## 15. AI Investment Intelligence Intent
Help identify **possible investment opportunities worthy of further research** using current markets, economic conditions, fundamentals, valuations, trends, historical data, portfolio composition, user objectives and risk profile.

The system explains why an opportunity surfaced instead of simply presenting a recommendation.

## 16. AI Opportunity Analysis
Each opportunity should contain:
- Asset/instrument and asset class
- Why it surfaced
- Supporting evidence
- Risk level and key risks
- Research/investment horizon
- Portfolio and diversification impact
- Assumptions
- Data-as-of timestamp
- Evidence/source references
- Research, Compare and Simulate actions

## 17. Investment Opportunity Pipeline
```text
Investment Universe
-> Eligibility Filters
-> Market/Fundamental/Macro Data
-> Quantitative Analysis
-> Explainable Opportunity Scoring
-> Portfolio Compatibility
-> Risk Analysis
-> Supporting Research
-> LLM Explanation
-> Validated Investment Opportunity
```

The LLM must not independently invent market data, metrics or expected returns.

## 18. Portfolio Doctor
Evaluate concentration, asset allocation, sector/geographic/currency exposure, liquidity, volatility, income concentration and goal alignment. Generate observations and alternative scenarios without automatically executing trades.

## 19. Compare Investments
Compare potential investments using risk, volatility, income yield, liquidity, fees, historical performance, asset class, geography, currency, horizon and diversification impact. Future returns must be expressed as assumptions/scenarios rather than facts.

## 20. Scenario Simulator
Potential investments can be passed to the deterministic forecasting engine to compare multiple return assumptions, contribution levels and horizons.

## 21. Market Intelligence Layer
Use provider abstractions for equity/ETF/crypto prices, FX, bonds, economic indicators, fundamentals, market news, research and appropriate real-estate information. Avoid hard dependency on one provider.

## 22. AI Architecture Intent
```text
Mobile App
-> WealthSphere API
-> AI Orchestrator
-> Authorization
-> Allow-Listed Tool
-> Structured Result
-> LLM
-> Validated Response
-> Mobile App
```

The LLM is never authoritative for balances, transaction history, calculations, market prices, FX rates or ownership.

## 23. Security Intent
Security is a primary architectural requirement:
- TLS and encryption at rest
- OAuth/OIDC and MFA
- Secure token storage
- Biometric application access
- Server-side authorization and resource ownership checks
- Rate limiting
- Audit trails
- Secrets management
- Backups and disaster recovery
- Secure logging
- Dependency/container/static security scanning
- Mobile and API security testing

Cross-user portfolio access is a critical security failure.

## 24. Technology Intent
Preferred initial stack:
- Mobile: Flutter, Dart, Riverpod, GoRouter, Dio, Freezed, Secure Storage, Local Authentication
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- Data: PostgreSQL, pgvector, Redis
- Messaging: RabbitMQ/Celery
- AI: dedicated AI Orchestrator, OpenAI API, retrieval and tool calling
- Identity: Keycloak, OAuth 2.1/OIDC
- DevOps: Docker, GitHub Actions, Terraform
- Observability: OpenTelemetry, Prometheus, Grafana

## 25. Cloud Intent
Remain deployable to AWS, Google Cloud or OCI. Isolate cloud-specific dependencies. Prefer managed containers initially; introduce Kubernetes when scale/availability/operational needs justify it.

## 26. Architectural Principle
Begin as a **modular monolith**, not an unnecessary collection of microservices. Preserve clear domain boundaries for Identity, Portfolio, Investments, Transactions, Analytics, Forecasting, Goals, Net Worth, Market Data, Notifications and AI.

## 27. Data Integrity Principle
Use UUID primary keys, PostgreSQL NUMERIC/DECIMAL for money, append-oriented transaction history, timestamped valuations/FX, migrations, referential integrity and idempotent integration processing.

## 28. AI Safety Principle
Always distinguish:
- **Observed Data:** trusted external/internal facts.
- **Calculated Data:** deterministic WealthSphere calculations.
- **Assumptions:** user-selected or explicitly sourced modelling inputs.
- **AI Interpretation:** LLM explanation based on the above.

## 29. Explainability Principle
The system must be able to explain why an opportunity was surfaced, including selection criteria, market evidence, portfolio relevance, risks, sources and timestamp.

## 30. Initial Non-Goals
The initial release is not a bank, broker, exchange, high-frequency trading system or autonomous robo-adviser. Focus on **Tracking + Measurement + Intelligence + Forecasting + Research + Decision Support**.

_Clarification (approved 2026-10-09, ADR-0009): the optional Forex module in section 34 is decision support and paper trading only. It does not change these non-goals: no order execution, no brokerage, no autonomous or copy trading._

## 31. Development Philosophy
For each feature:
```text
Understand -> Design -> Implement -> Test -> Secure -> Observe -> Document
```
Do not modify unrelated functionality merely to complete a scoped task.

## 32. Development Priority
```text
Phase 0  Engineering Foundation
Phase 1  Identity + Portfolio
Phase 2  Investments + Transactions
Phase 3  Analytics + Multi-Currency
Phase 4  Compounding + Goals
Phase 5  Net Worth + Passive Income
Phase 6  Market Data
Phase 7  AI Tool Architecture
Phase 8  AI Wealth Copilot
Phase 9  AI Investment Intelligence
Phase 10 Production Hardening
         -> Android + iOS Production Release
```

## 33. Final Solution Intent
WealthSphere should evolve into a **Personal Wealth Operating System**.

Portfolio Management tells users what they own. Analytics explains performance. Net Worth shows their overall financial position. Goals define where they want to go. Compounding and forecasting show possible paths. Market Intelligence provides awareness. AI Investment Intelligence discovers opportunities worthy of investigation. Portfolio Doctor identifies risks and imbalances. Scenario Simulation demonstrates potential impacts. WealthSphere AI brings these capabilities together conversationally.

The objective is not for AI to make financial decisions on behalf of the user. The objective is to give the user a substantially better understanding of wealth, alternatives, risks, opportunities and possible future outcomes so they can make better-informed decisions.


## 34. Forex Market Intelligence Module (approved extension, ADR-0009)
_Status: approved by the user 2026-10-09 (ADR-0009, phase P13). Not part of the core release path (P00-P12 and P14-P16); it is planned as phase P13, between the AI phases and cloud infrastructure._

**Intent.** Help users study the foreign-exchange market with timestamped market data, deterministic technical analysis, probabilistic forecasts with honest validation, a transparent opportunity ranking, trade risk management, backtesting and paper trading, explained by the AI Copilot through allow-listed tools.

**Scope.** Major, minor and selected emerging-market pairs (configurable universe); live bid/ask, spread in pips, change, session, volatility and feed status; timeframes 1m to 1M; indicators and market structure; economic calendar; forecasts for 15m, 1h, 4h, 24h and 1w horizons; an Opportunity Ranking Dashboard of research candidates (pair, market condition, opportunity type, risk, score with factors); a risk calculator; backtesting; paper trading with a journal; an AI Forex Copilot; alerts.

**Boundaries (non-negotiable).**
- Decision support and paper trading only. No live trade execution, broker trading credentials or automated trading without a separate approved phase, regulatory review and dedicated trading risk controls.
- No guaranteed-return language. Forecasts and scores are model outputs; probabilities are labelled "Requires calibration" until calibration is established and are never described as success rates.
- Tradable quotes, indicative rates, delayed and simulated prices are distinguished everywhere and never shown as live executable quotes; prices are never invented when a provider is down.
- Paper balances never enter net worth, holdings or real analytics, and PAPER TRADING is labelled throughout.
- The backend computes prices, indicators, forecasts, risk and backtests; the LLM only explains tool results and separates facts, calculations, assumptions and interpretation.
- Position sizing never assumes a fixed pip value; stop-loss orders do not guarantee a maximum loss, and leverage and margin warnings are shown.

**Quality.** Gates QG-FX-01…08 (QG-13…QG-20) in QUALITY_GATES.md; plan in EXECUTION_PLAN.md phase P13; design in docs/design/forex-technical-design.md.

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
