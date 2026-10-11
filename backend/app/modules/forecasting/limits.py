"""What the forecast API accepts (P06-T02). The mobile calculator mirrors these limits in
mobile/wealthsphere_app/lib/features/calculator/domain/forecast_input_limits.dart, and
tests/forecasting/test_limits_shared.py fails the build if the two differ."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Limit:
    minimum: Decimal
    maximum: Decimal
    decimals: int = 2  # most decimal places accepted


INITIAL_INVESTMENT = Limit(Decimal(0), Decimal(1_000_000_000))
CONTRIBUTION = Limit(Decimal(0), Decimal(10_000_000))
RETURN_RATE = Limit(Decimal(-20), Decimal(50))  # negative returns model losses
YEARS = Limit(Decimal(1), Decimal(60), decimals=0)
CONTRIBUTION_GROWTH = Limit(Decimal(0), Decimal(20))
INFLATION = Limit(Decimal(0), Decimal(30))
ANNUAL_FEE = Limit(Decimal(0), Decimal(5))
# Goal targets (the calculator has no target field yet; goals use it from P06-T06).
TARGET = Limit(Decimal("0.01"), Decimal(10_000_000_000))

NOTICE = (
    "Projections are illustrative scenarios based on the assumptions shown. "
    "They are not guaranteed."
)
