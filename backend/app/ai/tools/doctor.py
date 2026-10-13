"""Portfolio Doctor tool (P12-T01): the deterministic findings of one of the user's portfolios, for
the assistant to explain. The tool returns exactly what `POST /api/v1/ai/portfolio-doctor`
returns; the model never computes, adds or grades findings. Owner-scoped like the API."""

import uuid

from pydantic import Field

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.modules.doctor.schemas import NOTICE, DoctorOut, doctor_out
from app.modules.doctor.service import DoctorService


class DiagnosisArguments(ToolArguments):
    portfolio_id: uuid.UUID = Field(description="One of the user's portfolios")


class DiagnosisResult(ToolData, DoctorOut):
    """The API's answer, with the tool envelope (as_of, complete)."""

    notice: str = NOTICE


async def get_portfolio_diagnosis(ctx: ToolContext, args: DiagnosisArguments) -> DiagnosisResult:
    result = await DoctorService(ctx.session).portfolio(ctx.user_id, args.portfolio_id, ctx.now())
    out = doctor_out(result.portfolio_id, result.as_of, result.diagnosis, result.inputs.complete)
    return DiagnosisResult.model_validate(out.model_dump())


def register_doctor_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_portfolio_diagnosis",
            "Portfolio Doctor: the health checks of one of the user's portfolios (concentration, "
            "currency exposure, liquidity, volatility, drawdown, income dependence, goal "
            "alignment, data completeness), each with a severity against stated thresholds, and "
            "hypothetical scenarios that are never orders. Explain these findings; do not add, "
            "change or grade any.",
            DiagnosisArguments,
            DiagnosisResult,
            get_portfolio_diagnosis,
        )
    )
