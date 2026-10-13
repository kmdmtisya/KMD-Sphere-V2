"""A real backend for the end-to-end journeys (P09-T10): a throwaway migrated database, seeded for
the journeys, served over HTTP.

    uv run python -m tests.e2e_server --port 8765 --out e2e.json

It prints nothing secret. The output file holds the URL and a test-signed token for the seeded
user (tokens are accepted by the test verifier only; the identity provider itself is covered by the
Keycloak check in tests/test_identity_keycloak_live.py). Stop it with Ctrl+C: the database is
dropped on the way out.

Not a test module: pytest does not collect it (no `test_` prefix).
"""

import argparse
import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import uvicorn
from alembic import command
from alembic.config import Config

from app.ai.providers.fake import FakeLlmProvider, text_reply, tool_reply
from app.ai.providers.models import ChatRequest, ChatResponse
from app.core.config import Settings
from app.main import create_app
from app.modules.alerts.evaluation import evaluate_alerts
from app.modules.notifications.push import NullPushSender
from tests import auth_helpers as ah

BACKEND = Path(__file__).resolve().parents[1]
SUBJECT = "e2e-alice"


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def scripted_assistant() -> FakeLlmProvider:
    """A model that reads the net worth and answers with a checked, figure-free answer. The real
    models are never called from the end-to-end run."""

    def reply(request: ChatRequest) -> ChatResponse:
        if any(m.role == "tool" for m in request.messages):
            return text_reply(
                json.dumps(
                    {
                        "observed": [
                            {"text": "Your net worth was retrieved.", "source": "get_net_worth"}
                        ],
                        "calculated": [],
                        "assumptions": [],
                        "interpretation": "A snapshot of your own records, not a forecast.",
                    }
                )
            )
        return tool_reply("get_net_worth")

    return FakeLlmProvider([reply] * 200)


E2E_RATES = {
    "AED": "3.6725",
    "AUD": "1.5112",
    "CAD": "1.3705",
    "CHF": "0.8634",
    "EUR": "0.9216",
    "GBP": "0.7712",
    "JPY": "149.83",
    "KES": "129.15",
    "ZAR": "17.8421",
}


async def seed(app: Any, db: asyncpg.Connection) -> dict[str, Any]:
    """Alice has a portfolio with cash and one priced stock, a goal, a device and a fired alert."""
    token = ah.token(
        SUBJECT, email="alice@example.test", exp=int(datetime.now(UTC).timestamp()) + 8 * 3600
    )
    h = ah.bearer(token)
    today = datetime.now(UTC).date()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://seed"
    ) as http:
        me = (await http.get("/api/v1/me", headers=h)).json()
        await http.patch("/api/v1/me/preferences", headers=h, json={"display_name": "Alice"})
        cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
        asset = str(
            await db.fetchval(
                "INSERT INTO assets (asset_class_id, symbol, name, currency) "
                "VALUES ($1, 'E2E', 'E2E Corp', 'USD') RETURNING id",
                cls,
            )
        )
        pid = (
            await http.post(
                "/api/v1/portfolios", headers=h, json={"name": "Retirement", "base_currency": "USD"}
            )
        ).json()["id"]
        day = (today - timedelta(days=30)).isoformat()
        for body in (
            {
                "transaction_type": "DEPOSIT",
                "trade_date": day,
                "currency": "USD",
                "gross_amount": m("10000.00"),
            },
            {
                "transaction_type": "BUY",
                "trade_date": day,
                "currency": "USD",
                "asset_id": asset,
                "quantity": "10",
                "unit_price": m("100"),
            },
        ):
            r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)
            assert r.status_code == 201, r.text
        now = datetime.now(UTC)
        # Reporting-currency rates (P11-T09): USD against the other launch currencies.
        for quote, rate in E2E_RATES.items():
            await db.execute(
                "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, "
                "rate_timestamp, retrieved_at) VALUES ('USD', $1, $2::numeric, 'e2e', $3, $3)",
                quote,
                rate,
                now - timedelta(minutes=5),
            )
        await db.execute(
            "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, as_of, "
            "retrieved_at) VALUES ($1, 120, 'USD', 'quote', 'e2e', $2, $2)",
            uuid.UUID(asset),
            now - timedelta(minutes=5),
        )
        goal = await http.post(
            "/api/v1/goals",
            headers=h,
            json={
                "name": "House deposit",
                "goal_type": "house_deposit",
                "target": m("50000.00"),
                "target_date": (today + timedelta(days=900)).isoformat(),
                "portfolio_id": pid,
                "assumptions": {"contribution": m("500.00"), "returns": {"base": "6"}},
            },
        )
        assert goal.status_code == 201, goal.text
        await http.post(
            "/api/v1/devices",
            headers=h,
            json={"platform": "android", "token": "e2e-device-token-1"},
        )
        alert = await http.post(
            "/api/v1/alerts",
            headers=h,
            json={
                "alert_type": "price_above",
                "asset_id": asset,
                "threshold_price": m("110"),
                "note": "e2e",
            },
        )
        assert alert.status_code == 201, alert.text
    async with app.state.db.session_factory() as session:
        result = await evaluate_alerts(session, sender=NullPushSender())
    assert result.triggered >= 1, result
    return {
        "token": token,
        "user_id": me["id"],
        "portfolio_id": pid,
        "asset_id": asset,
        "holdings_value": "1200.00",
    }


async def main(port: int, out: Path, log_level: str) -> None:
    base = Settings(environment="test")
    name = f"ws_e2e_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(base.database_dsn, timeout=5)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    settings = base.model_copy(
        update={
            "postgres_db": name,
            "oidc_issuer": "",
            "rate_limit_storage": "memory",
            # All nine journeys run as one seeded user, so a whole UI run exceeds the production
            # per-account budget (120 a minute) and journey 9 met 429s. Limiting stays on; the
            # budgets themselves are tested in tests/test_api_protection.py.
            "rate_limit_user_requests": 600,
            "analytics_cache": "memory",
            # FX refreshes use the offline fake provider: the run never calls a real vendor.
            "market_data_mode": "fake",
        }
    )
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["sqlalchemy_url"] = settings.sqlalchemy_url
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
        app = create_app(
            settings,
            readiness_checks={},
            token_verifier=ah.verifier(),
            llm=scripted_assistant(),
        )
        db = await asyncpg.connect(settings.database_dsn, timeout=5)
        try:
            seeded = await seed(app, db)
        finally:
            await db.close()
        text = json.dumps({"api_url": f"http://127.0.0.1:{port}", **seeded})
        await asyncio.to_thread(out.write_text, text, encoding="utf-8")
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level=log_level)
        )
        await server.serve()
    finally:
        admin = await asyncpg.connect(base.database_dsn, timeout=5)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--out", type=Path, default=Path("e2e.json"))
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(args.port, args.out, args.log_level))
