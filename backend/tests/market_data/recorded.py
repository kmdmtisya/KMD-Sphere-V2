"""An offline `HttpClient` that replays recorded fixtures (P08-T03.2)."""

from dataclasses import dataclass, field
from pathlib import Path

from app.modules.market_data.providers.http import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class Call:
    url: str
    params: dict[str, str]
    headers: dict[str, str]


@dataclass
class Route:
    path: str
    response: HttpResponse
    params: dict[str, str] = field(default_factory=dict)


class RecordedClient:
    """Answers by URL path and a subset of the query parameters. An unmatched request fails the
    test loudly: contract tests must never reach the network."""

    def __init__(self, routes: list[Route]) -> None:
        self.routes = routes
        self.calls: list[Call] = []

    async def get(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        sent = params or {}
        self.calls.append(Call(url, dict(sent), dict(headers or {})))
        for route in self.routes:
            if url.endswith(route.path) and all(sent.get(k) == v for k, v in route.params.items()):
                return route.response
        raise AssertionError(f"no recorded response for {url} {sent}")


def ok(text: str) -> HttpResponse:
    return HttpResponse(200, text)
