"""The routing runner (P10-T09.5): proven here with stand-in models, because CI has no real one.
The 95% threshold is measured against a real provider before release (tests/ai_eval/live.py)."""

import pytest

from app.ai.providers.fake import FakeLlmProvider, text_reply
from app.ai.providers.models import ChatRequest, ChatResponse, ToolCall
from app.ai.tools.factory import build_tool_registry
from app.core.config import Settings
from tests.ai_eval.harness import judge, load
from tests.ai_eval.live import chosen_tools, evaluate_routing

pytestmark = pytest.mark.security


def router(answers: dict[str, list[str]]) -> FakeLlmProvider:
    """A stand-in that routes each question as the dataset says (or as `answers` overrides)."""

    def reply(request: ChatRequest) -> ChatResponse:
        question = request.messages[-1].content
        tools = answers.get(question, [])
        return ChatResponse(
            content="" if tools else "ok",
            tool_calls=tuple(ToolCall(f"c{i}", t, {}) for i, t in enumerate(tools)),
            provider="fake",
            model="fake-1",
        )

    return FakeLlmProvider([reply] * 400)


SPECS = build_tool_registry(Settings()).specs()


async def test_a_model_that_routes_as_the_dataset_says_scores_one_hundred_percent() -> None:
    cases = load("routing")
    perfect = router({c["question"]: c["expected_tools"] for c in cases})
    verdicts = await evaluate_routing(perfect, SPECS, cases)
    assert all(verdicts.values())
    judge("routing", verdicts, mode="harness")


async def test_a_model_that_never_uses_tools_fails_the_threshold() -> None:
    cases = load("routing")
    verdicts = await evaluate_routing(router({}), SPECS, cases)
    with pytest.raises(AssertionError, match="threshold 95%"):
        judge("routing", verdicts, mode="harness")
    # the clean run recorded by the other test is what the report shows
    perfect = router({c["question"]: c["expected_tools"] for c in cases})
    judge("routing", await evaluate_routing(perfect, SPECS, cases), mode="harness")


async def test_the_runner_sends_the_real_tool_descriptions_and_only_the_question() -> None:
    llm = FakeLlmProvider([text_reply("ok")])
    await chosen_tools(llm, SPECS, "What is my net worth?")
    request = llm.requests[0]
    assert {t.name for t in request.tools} == {s.name for s in SPECS}
    assert [m.role for m in request.messages] == ["system", "user"]
    assert request.messages[1].content == "What is my net worth?"
