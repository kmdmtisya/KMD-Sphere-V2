"""Builds the registry the orchestrator uses. The tool modules (P10-T03, T04, later P12) add their
tools here; nothing else registers tools."""

from app.ai.tools.core_read import register_core_read_tools
from app.ai.tools.currency import register_currency_tools
from app.ai.tools.doctor import register_doctor_tools
from app.ai.tools.forecast import register_forecast_tools
from app.ai.tools.forex import register_forex_tools
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.research import register_research_tools
from app.core.config import Settings


def build_tool_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry(
        calls_per_minute=settings.ai_tool_calls_per_minute,
        default_timeout_seconds=settings.ai_tool_timeout_seconds,
        max_result_bytes=settings.ai_tool_max_result_bytes,
    )
    register_core_read_tools(registry)
    register_forecast_tools(registry)
    register_currency_tools(registry)
    register_doctor_tools(registry)
    register_research_tools(registry)
    if settings.forex_enabled:  # DEC-23: no forex tool while the module is off
        register_forex_tools(registry, settings)
    return registry
