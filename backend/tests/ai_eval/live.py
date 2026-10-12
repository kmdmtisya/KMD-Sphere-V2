"""The pre-release run against a real provider (P10-T09.5, DEC-17).

CI cannot measure how well a real model chooses tools: it runs against the scripted fake. Before a
release, an operator runs this against the configured provider and records the result:

    cd backend && AI_PROVIDER=openai OPENAI_API_KEY=... AI_OPENAI_MODEL=... \\
        uv run python -m tests.ai_eval.live

It sends each routing question with the real tool descriptions and compares the tools the model
asks for in its first round with the dataset (threshold 95%). It sends only the synthetic questions
of the dataset, never user data, and needs the provider terms review recorded in ADR-0017 first.
The function `evaluate_routing` is the same code CI exercises against a stand-in model."""

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from app.ai.orchestrator.prompt import system_prompt
from app.ai.providers.base import LlmProvider
from app.ai.providers.models import ChatRequest, Message
from app.ai.tools.base import ToolSpec
from tests.ai_eval.harness import THRESHOLDS, load


async def chosen_tools(llm: LlmProvider, specs: list[ToolSpec], question: str) -> set[str]:
    request = ChatRequest(
        (
            Message("system", system_prompt(datetime.now(UTC).date(), None)),
            Message("user", question),
        ),
        tuple(specs),
        512,
    )
    response = await llm.complete(request)
    return {call.name for call in response.tool_calls}


async def evaluate_routing(
    llm: LlmProvider, specs: list[ToolSpec], cases: list[dict[str, Any]]
) -> dict[str, bool]:
    verdicts: dict[str, bool] = {}
    for case in cases:
        verdicts[case["id"]] = await chosen_tools(llm, specs, case["question"]) == set(
            case["expected_tools"]
        )
    return verdicts


async def main() -> int:
    from app.ai.providers.registry import build_llm
    from app.ai.tools.factory import build_tool_registry
    from app.core.config import get_settings

    settings = get_settings()
    if settings.ai_provider == "fake":
        print("Set AI_PROVIDER to a real provider (and its key and model).")
        return 2
    verdicts = await evaluate_routing(
        build_llm(settings), build_tool_registry(settings).specs(), load("routing")
    )
    failures = sorted(k for k, ok in verdicts.items() if not ok)
    rate = 1 - len(failures) / len(verdicts)
    rule = THRESHOLDS["routing"]
    print(
        f"routing: {len(verdicts) - len(failures)}/{len(verdicts)} ({rate:.1%}); "
        f"threshold {rule.minimum_rate:.0%}"
    )
    if failures:
        print("failing cases:", ", ".join(failures))
    return 0 if rate >= rule.minimum_rate else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
