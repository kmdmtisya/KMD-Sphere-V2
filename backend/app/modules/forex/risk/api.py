"""Trade risk calculator API (P13-T07.5, design section 9). Behind the forex flag; the inputs are
the caller's own hypothetical trade and nothing is stored or placed. The calculation is in
`risk.service`, shared with the Forex Copilot (P13-T10).

The pip value is never a constant: it is converted from the quote currency into the account
currency at a stored rate whose path, time and data types are returned. Every response carries
the warnings that apply and the disclosures that always apply (a stop can slip or gap)."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Request

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.risk.schemas import (
    ForexContractSpecOut,
    ForexContractSpecsOut,
    ForexRiskOut,
    ForexRiskRequest,
)
from app.modules.forex.risk.service import calculate_trade, spec_ref
from app.modules.forex.risk.specs import active_spec

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("trade or no stored conversion rate"),
    **not_found("forex module (switched off)"),
}


@router.post(
    "/risk/calculate",
    response_model=ForexRiskOut,
    summary="Position size, pip value, loss, profit, costs, margin and exposure of a trade idea",
    description="Sizes a hypothetical position so the planned loss at the stop, including costs, "
    "stays within the risk percent; the size is rounded down to the lot step. The pip value is "
    "converted into the account currency at a stored rate whose path and freshness are returned. "
    "Warnings cover limits, margin, leverage, rate quality and unreviewed specifications. Nothing "
    "is stored or placed.",
    responses=RESPONSES,
)
async def calculate(
    request: Request, body: ForexRiskRequest, _: ForexUser, session: SessionDep
) -> ForexRiskOut:
    settings: Settings = request.app.state.settings
    return await calculate_trade(session, settings, body, datetime.now(UTC))


@router.get(
    "/contract-specs",
    response_model=ForexContractSpecsOut,
    summary="The contract specifications the risk calculator uses",
    description="The active, versioned specification of each active pair: contract size, lot "
    "step and limits, margin rate (and the maximum leverage it implies), commission and the "
    "slippage assumption, with the review status.",
    responses={**UNAUTHORIZED, **not_found("forex module (switched off)")},
)
async def contract_specs(_: ForexUser, session: SessionDep) -> ForexContractSpecsOut:
    items = []
    for pair in await active_instruments(session):
        row = await active_spec(session, pair.code)
        if row is None:
            continue
        ref = spec_ref(row)
        items.append(
            ForexContractSpecOut(
                instrument=row.instrument,
                version=row.version,
                contract_size=row.contract_size,
                lot_step=row.lot_step,
                min_lots=row.min_lots,
                max_lots=row.max_lots,
                margin_rate=row.margin_rate,
                max_leverage=(Decimal(1) / row.margin_rate).quantize(Decimal("0.01")),
                commission_per_lot_side=row.commission_per_lot_side,
                slippage_pips=row.slippage_pips,
                review_status=ref.review_status,
                reviewed_by=ref.reviewed_by,
                reviewed_at=ref.reviewed_at,
            )
        )
    return ForexContractSpecsOut(items=items)
