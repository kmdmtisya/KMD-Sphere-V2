"""Forex Intelligence (P13, ADR-0009): market data, analysis, forecasts, signals, risk, backtests
and paper trading for currency pairs. Decision support and paper trading only: there is no order
path, no broker connection and no trading credential (docs/design/forex-reconciliation.md).

Separate from `app.modules.fx`, which converts the user's own money into a reporting currency:
the two share no tables, services or labels."""
