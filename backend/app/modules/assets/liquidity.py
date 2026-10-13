"""How quickly each asset class can usually become cash (P12-T01, shared with the investment
universe in P12-T02). An assumption about the class, stated wherever it is used; not a fact about a
particular holding."""

from enum import StrEnum


class Liquidity(StrEnum):
    """How quickly an asset class can usually become cash. An assumption about the class, not
    a fact about the user's holding (a listed share can still be hard to sell)."""

    IMMEDIATE = "immediate"  # cash, money market funds: same or next day
    MARKET = "market"  # listed and pooled assets: days
    TERM = "term"  # fixed deposits, SACCO, pension: locked until maturity, notice or rules
    ILLIQUID = "illiquid"  # property, private holdings: months, if at all
    UNKNOWN = "unknown"  # custom assets


LIQUIDITY_BY_CLASS: dict[str, Liquidity] = {
    "cash": Liquidity.IMMEDIATE,
    "money_market_fund": Liquidity.IMMEDIATE,
    "stock": Liquidity.MARKET,
    "etf": Liquidity.MARKET,
    "bond": Liquidity.MARKET,
    "mutual_fund": Liquidity.MARKET,
    "reit": Liquidity.MARKET,
    "cryptocurrency": Liquidity.MARKET,
    "commodity": Liquidity.MARKET,
    "fixed_deposit": Liquidity.TERM,
    "sacco": Liquidity.TERM,
    "pension": Liquidity.TERM,
    "real_estate": Liquidity.ILLIQUID,
    "private_business": Liquidity.ILLIQUID,
    "private_equity": Liquidity.ILLIQUID,
    "custom": Liquidity.UNKNOWN,
}
ACCESSIBLE = frozenset({Liquidity.IMMEDIATE, Liquidity.MARKET})
LIQUIDITY_ASSUMPTION = (
    "Liquidity is assumed from the asset class: cash and money market funds immediate; listed "
    "and pooled assets within days; fixed deposits, SACCO and pension holdings locked until "
    "maturity or notice; property and private holdings illiquid; custom assets unknown."
)
