"""The AI tool framework (P10-T02): context, allow-list, validation, audit, limits."""

import ast
import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.tools.base import (
    ALLOWED_TOOLS,
    Tool,
    ToolArguments,
    ToolContext,
    ToolData,
)
from app.ai.tools.registry import AUDIT_ACTION, ToolRegistry
from app.core.audit import hash_arguments
from app.core.authz import ResourceNotFoundError
from app.core.config import Settings
from app.core.correlation import correlation_id_var
from app.core.errors import InvalidValueError
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
APP = Path(__file__).resolve().parents[2] / "app"
DOC = Path(__file__).resolve().parents[3] / "docs" / "ai-governance.md"
USER = uuid.uuid4()
NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


class Args(ToolArguments):
    portfolio_id: uuid.UUID | None = None
    limit: int = Field(default=5, ge=1, le=20)


class Data(ToolData):
    value: str


async def ok_handler(ctx: ToolContext, args: Args) -> Data:
    return Data(as_of=NOW, value=f"limit={args.limit}")


def tool(handler: Any = ok_handler, name: str = "get_net_worth", **kw: Any) -> Tool:
    return Tool(name, "A test tool", Args, Data, handler, **kw)


@pytest.fixture
async def sessions(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def audited(raw: asyncpg.Connection, user: uuid.UUID) -> list[asyncpg.Record]:
    return await raw.fetch(
        "SELECT actor_type, actor_user_id, action, resource_id, outcome, correlation_id, "
        "details FROM audit_events WHERE actor_user_id = $1 AND action = $2 ORDER BY occurred_at",
        user,
        AUDIT_ACTION,
    )


def registry(*tools: Tool, **kw: Any) -> ToolRegistry:
    r = ToolRegistry(**kw)
    for t in tools or (tool(),):
        r.register(t)
    return r


# ------------------------------------------------------------------------------- context
async def test_a_call_without_user_context_is_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    called = False

    async def handler(ctx: ToolContext, args: Args) -> Data:
        nonlocal called
        called = True
        return Data(as_of=NOW, value="x")

    outcome = await registry(tool(handler)).execute("get_net_worth", {}, None)
    assert not outcome.ok and outcome.error_code == "no_user_context"
    assert not called


async def test_the_model_cannot_supply_or_change_the_user(
    sessions: async_sessionmaker[AsyncSession],
    raw: asyncpg.Connection,
) -> None:
    seen: list[uuid.UUID] = []

    async def handler(ctx: ToolContext, args: Args) -> Data:
        seen.append(ctx.user_id)
        return Data(as_of=NOW, value="x")

    user = uuid.uuid4()
    async with sessions() as s:
        r = registry(tool(handler))
        for hostile in (
            {"user_id": str(uuid.uuid4())},
            {"userId": str(uuid.uuid4())},
            {"owner": "someone-else"},
        ):
            outcome = await r.execute("get_net_worth", hostile, ToolContext(user, s))
            assert outcome.error_code == "invalid_arguments"
    assert seen == [], "the handler never ran with a model-supplied identity"
    assert len(await audited(raw, user)) == 3


def test_argument_schemas_have_no_user_field() -> None:
    schema = Args.model_json_schema()
    assert not any("user" in name.lower() for name in schema["properties"])


# --------------------------------------------------------------------------------- audit
async def test_every_call_emits_an_audit_event_with_args_hash_and_correlation_id(
    sessions: async_sessionmaker[AsyncSession],
    raw: asyncpg.Connection,
) -> None:
    user = uuid.uuid4()
    arguments = {"limit": 7}
    async with sessions() as s:
        ctx = ToolContext(user, s, correlation_id="corr-123", model="fake-1", provider="fake")
        outcome = await registry().execute("get_net_worth", arguments, ctx)
    assert outcome.ok and outcome.data is not None and outcome.data["value"] == "limit=7"
    [row] = await audited(raw, user)
    assert row["actor_type"] == "ai"
    assert row["outcome"] == "success"
    assert row["resource_id"] == "get_net_worth"
    assert row["correlation_id"] == "corr-123"
    details = row["details"]
    text = details if isinstance(details, str) else str(details)
    assert hash_arguments(arguments) in text
    assert "limit" not in text.replace("limit=7", ""), "the arguments themselves are not stored"
    assert "fake-1" in text and "fake" in text


async def test_the_correlation_id_of_the_request_is_used_when_the_context_has_none(
    sessions: async_sessionmaker[AsyncSession],
    raw: asyncpg.Connection,
) -> None:
    user = uuid.uuid4()
    token = correlation_id_var.set("from-request")
    try:
        async with sessions() as s:
            await registry().execute("get_net_worth", {}, ToolContext(user, s))
    finally:
        correlation_id_var.reset(token)
    [row] = await audited(raw, user)
    assert row["correlation_id"] == "from-request"


async def test_refusals_are_audited_too(
    sessions: async_sessionmaker[AsyncSession],
    raw: asyncpg.Connection,
) -> None:
    user = uuid.uuid4()
    async with sessions() as s:
        outcome = await registry().execute("run_sql", {"query": "select 1"}, ToolContext(user, s))
    assert outcome.error_code == "unknown_tool"
    [row] = await audited(raw, user)
    assert row["outcome"] == "denied"
    assert "select 1" not in str(row["details"]), "the arguments of a refused call are not stored"


# --------------------------------------------------------------------------- allow-list
def test_only_listed_tools_can_be_registered() -> None:
    r = ToolRegistry()
    for bad in ("run_sql", "shell", "fetch_url", "write_file", "place_order", "GET_NET_WORTH"):
        with pytest.raises(ValueError, match="allow-list"):
            r.register(tool(name=bad))


def test_a_tool_cannot_be_registered_twice() -> None:
    r = registry()
    with pytest.raises(ValueError, match="already registered"):
        r.register(tool())


def test_the_code_and_the_document_list_the_same_tools() -> None:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## 1. Tool allow-list")[1].split("### Tool contract")[0]
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.M))
    assert documented == set(ALLOWED_TOOLS)


def test_the_specs_given_to_the_model_hold_only_name_description_and_schema() -> None:
    [spec] = registry().specs()
    assert (spec.name, spec.description) == ("get_net_worth", "A test tool")
    assert set(spec.parameters["properties"]) == {"portfolio_id", "limit"}


# ------------------------------------------------------------------------ the forbidden
FORBIDDEN_IMPORTS = {
    "subprocess",
    "os",
    "pty",
    "shlex",
    "socket",
    "ssl",
    "http",
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "ftplib",
    "smtplib",
    "ctypes",
    "importlib",
    "asyncpg",
    "psycopg",
    "psycopg2",
    "sqlite3",
}
FORBIDDEN_NAMES = {"eval", "exec", "compile", "__import__", "open"}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_IMPORTS]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                found.append(node.module)
            if node.module.startswith("sqlalchemy") and any(
                a.name in ("text", "literal_column") for a in node.names
            ):
                found.append(f"{node.module}.text")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append(node.id)
    return found


def test_the_tool_layer_has_no_sql_shell_or_network_access() -> None:
    offenders = {
        str(p.relative_to(APP)): v
        for p in (APP / "ai" / "tools").rglob("*.py")
        if (v := _violations(p))
    }
    assert offenders == {}


def test_the_guard_sees_forbidden_code(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import subprocess\nfrom sqlalchemy import text\nexec('1')\n")
    assert {"subprocess", "sqlalchemy.text", "exec"} <= set(_violations(bad))


# ------------------------------------------------------------------- validation, limits
async def test_arguments_are_validated_with_bounds(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        r = registry()
        ctx = ToolContext(USER, s)
        for bad in ({"limit": 0}, {"limit": 999}, {"limit": "many"}, {"portfolio_id": "nope"}):
            assert (await r.execute("get_net_worth", bad, ctx)).error_code == "invalid_arguments"
        assert (await r.execute("get_net_worth", {"limit": 20}, ctx)).ok


async def test_a_missing_or_foreign_resource_is_just_not_found(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Data:
        raise ResourceNotFoundError("portfolio")

    async with sessions() as s:
        outcome = await registry(tool(handler)).execute("get_net_worth", {}, ToolContext(USER, s))
    assert (outcome.error_code, outcome.error_message) == ("not_found", "Not found.")


async def test_a_business_rule_error_is_a_plain_invalid(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Data:
        raise InvalidValueError("secret detail about row 42")

    async with sessions() as s:
        outcome = await registry(tool(handler)).execute("get_net_worth", {}, ToolContext(USER, s))
    assert outcome.error_code == "invalid"
    assert "secret" not in str(outcome.for_model())


async def test_an_unexpected_error_never_reaches_the_model(
    sessions: async_sessionmaker[AsyncSession],
    raw: asyncpg.Connection,
) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Data:
        raise RuntimeError("password=hunter2 in /srv/app/secret.py")

    user = uuid.uuid4()
    async with sessions() as s:
        outcome = await registry(tool(handler)).execute("get_net_worth", {}, ToolContext(user, s))
    assert outcome.error_code == "internal"
    assert "hunter2" not in str(outcome.for_model())
    [row] = await audited(raw, user)
    assert row["outcome"] == "failure"
    assert "hunter2" not in str(row["details"])


async def test_a_slow_tool_times_out(sessions: async_sessionmaker[AsyncSession]) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Data:
        await asyncio.sleep(5)
        return Data(as_of=NOW, value="late")

    async with sessions() as s:
        outcome = await registry(tool(handler, timeout_seconds=0.05)).execute(
            "get_net_worth", {}, ToolContext(USER, s)
        )
    assert outcome.error_code == "timeout"


async def test_an_oversized_result_is_refused(sessions: async_sessionmaker[AsyncSession]) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Data:
        return Data(as_of=NOW, value="x" * 5000)

    async with sessions() as s:
        outcome = await registry(tool(handler), max_result_bytes=1000).execute(
            "get_net_worth", {}, ToolContext(USER, s)
        )
    assert outcome.error_code == "too_large"


async def test_a_result_that_breaks_its_schema_is_not_returned(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async def handler(ctx: ToolContext, args: Args) -> Any:
        return ToolData(as_of=NOW)  # no `value`

    async with sessions() as s:
        outcome = await registry(tool(handler)).execute("get_net_worth", {}, ToolContext(USER, s))
    assert outcome.error_code == "internal"


async def test_calls_are_rate_limited_per_user(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    clock = [0.0]
    r = registry(calls_per_minute=3, clock=lambda: clock[0])
    async with sessions() as s:
        a, b = ToolContext(uuid.uuid4(), s), ToolContext(uuid.uuid4(), s)
        assert [(await r.execute("get_net_worth", {}, a)).ok for _ in range(4)] == [
            True,
            True,
            True,
            False,
        ]
        assert (await r.execute("get_net_worth", {}, b)).ok, "another user has their own budget"
        clock[0] = 61.0
        assert (await r.execute("get_net_worth", {}, a)).ok, "the window moves on"


async def test_money_in_results_stays_exact(sessions: async_sessionmaker[AsyncSession]) -> None:
    class Money(ToolData):
        amount: Decimal

    async def handler(ctx: ToolContext, args: Args) -> Money:
        return Money(as_of=NOW, amount=Decimal("0.10") + Decimal("0.20"))

    t = Tool("get_net_worth", "x", Args, Money, handler)
    async with sessions() as s:
        outcome = await registry(t).execute("get_net_worth", {}, ToolContext(USER, s))
    assert outcome.data is not None and outcome.data["amount"] == "0.30"


def test_the_factory_reads_the_limits_from_settings() -> None:
    from app.ai.tools.factory import build_tool_registry

    r = build_tool_registry(Settings(environment="test", ai_tool_calls_per_minute=7))
    assert r.names >= {"get_portfolio_summary", "get_net_worth"}
