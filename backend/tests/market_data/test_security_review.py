"""Market-data security and compliance checks (P08-T09): the provider keys never leave the
adapters, and the API exposes no provider data beyond what the licence review allows. The review
notes are in docs/security.md."""

import json
import logging
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.modules.market_data.ingestion import IngestFailure
from app.modules.market_data.providers.errors import ProviderError
from app.modules.market_data.providers.http import HttpResponse, HttpxClient
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.registry import build_providers
from app.modules.market_data.providers.resilience import FallbackChain, ResilientProvider
from tests.market_data.recorded import RecordedClient, Route
from tests.market_data.test_adapters import KEY, td

BACKEND = Path(__file__).resolve().parents[2]


class TestTwelveDataKeyNeverLeaks:
    @pytest.mark.parametrize(
        "response",
        [
            HttpResponse(401, f"bad key {KEY}"),
            HttpResponse(403, f'{{"message": "{KEY}"}}'),
            HttpResponse(429, ""),
            HttpResponse(500, KEY),
            HttpResponse(200, f'{{"status": "error", "code": 401, "message": "key {KEY}"}}'),
            HttpResponse(200, f'{{"status": "error", "code": 400, "message": "apikey {KEY}"}}'),
            HttpResponse(200, f"not json {KEY}"),
        ],
    )
    async def test_no_error_message_log_or_repr_holds_the_key(
        self, response: HttpResponse, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        provider = td(RecordedClient([Route("/quote", response)]))
        with pytest.raises(ProviderError) as caught:
            await provider.get_quote("GEQ", AssetKind.ETF)
        assert KEY not in str(caught.value) + repr(caught.value) + repr(provider)
        assert KEY not in caplog.text

    async def test_the_key_travels_in_a_header_never_in_the_url(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(500, text="")

        from app.modules.market_data.providers.twelvedata import TwelveDataProvider

        provider = TwelveDataProvider(
            SecretStr(KEY), HttpxClient(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(ProviderError):
            await provider.get_quote("GEQ", AssetKind.ETF)
        (request,) = seen
        assert KEY not in str(request.url)
        assert request.headers["authorization"] == f"apikey {KEY}"


class TestWhatTheRestOfTheSystemSees:
    def test_the_composed_providers_hold_no_readable_key(self) -> None:
        settings = Settings(
            market_data_mode="real",
            coingecko_api_key=SecretStr(KEY),
            twelvedata_api_key=SecretStr(KEY),
        )
        providers = build_providers(settings)
        assert set(providers.by_kind) == {
            AssetKind.EQUITY,
            AssetKind.ETF,
            AssetKind.INDEX,
            AssetKind.CRYPTO,
        }
        assert KEY not in repr(providers) + str(providers)
        for provider in {id(p): p for p in providers.by_kind.values()}.values():
            assert isinstance(provider, ResilientProvider)
            assert KEY not in repr(provider) + provider.name
        assert isinstance(providers.fx, FallbackChain)
        assert KEY not in repr(providers.fx) + providers.fx.name

    def test_an_ingest_failure_record_carries_only_the_error_type_and_message(self) -> None:
        failure = IngestFailure("GEQ", "ProviderAuthError", "twelvedata refused the credentials")
        assert KEY not in repr(failure)

    def test_the_example_environment_file_has_no_provider_key_values(self) -> None:
        text = (BACKEND.parent / ".env.example").read_text(encoding="utf-8")
        lines = {
            line.split("=", 1)[0]: line.split("=", 1)[1].strip()
            for line in text.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        for name in ("COINGECKO_API_KEY", "TWELVEDATA_API_KEY"):
            assert name in lines, f"{name} should be documented in .env.example"
            assert lines[name] == "", f"{name} must be empty in the example file"

    def test_no_source_or_compose_file_names_a_key_value(self) -> None:
        for path in [
            *BACKEND.joinpath("app").rglob("*.py"),
            *BACKEND.parent.glob("docker-compose*"),
        ]:
            text = path.read_text(encoding="utf-8")
            for name in ("COINGECKO_API_KEY", "TWELVEDATA_API_KEY"):
                for line in text.splitlines():
                    if name in line and "=" in line and not line.strip().startswith("#"):
                        value = line.split("=", 1)[1].strip().strip("\"'")
                        assert value in ("", "${" + name + "}"), f"{path.name}: {name} has a value"


class TestNoUnreviewedProviderDataLeavesTheApi:
    """Providers license display to our users, not redistribution. Only these routes carry
    market data, each per signed-in user and with provenance. A new route whose path mentions
    prices, quotes or rates fails here so the licence is re-checked first (docs/security.md)."""

    REVIEWED: ClassVar[set[str]] = {
        "/api/v1/fx-rates/{base}/{quote}",
        # P09-T07: per user, authenticated, stored (delayed) prices of an asset they can see.
        "/api/v1/assets/{asset_id}/prices",
        # P11-T03: per user, authenticated, stored reporting-currency rates with provider, type
        # and age. Display rights: ECB (copyright page not yet verified) and ExchangeRate-API
        # (terms not yet confirmed) are both re-checked at P11-T12 before production use.
        "/api/v1/fx/status",
        "/api/v1/fx/refresh",
        # P11-T04: per user, authenticated, rates and conversions from stored snapshots with
        # provenance; the same licence re-check at P11-T12 applies.
        "/api/v1/fx/rates",
        "/api/v1/fx/rates/{base}/{quote}",
        "/api/v1/fx/convert",
        # P11-T05: per user, authenticated, stored historical rates with provenance.
        "/api/v1/fx/history",
        # P13-T02: per user, authenticated, behind the forex flag. Fixture-only (DEC-19): the
        # only configurable provider is the in-house simulated feed, so no third-party data is
        # served and no licence applies yet. Wiring any real feed is blocked by QG-20.1 until the
        # vendor's streaming, display and redistribution licence is reviewed.
        "/api/v1/forex/quotes",
        "/api/v1/forex/candles",
    }
    MARKET_WORDS: ClassVar[tuple[str, ...]] = (
        "price",
        "quote",
        "fx",
        "rate",
        "market",
        "ticker",
        "candle",
        "history",
    )

    def test_only_reviewed_routes_serve_market_data(self) -> None:
        app: FastAPI = create_app(Settings(), readiness_checks={})
        paths = json.loads(json.dumps(app.openapi()))["paths"]
        flagged = {p for p in paths if any(w in p.lower() for w in self.MARKET_WORDS)}
        assert flagged == self.REVIEWED, (
            "a route that may serve market data was added or removed: re-check the provider "
            f"licences and update the reviewed list ({sorted(flagged ^ self.REVIEWED)})"
        )

    def test_every_reviewed_route_requires_a_signed_in_user(self) -> None:
        app: FastAPI = create_app(Settings(), readiness_checks={})
        spec = app.openapi()
        for path in self.REVIEWED:
            for operation in spec["paths"][path].values():
                assert "401" in operation["responses"], path
