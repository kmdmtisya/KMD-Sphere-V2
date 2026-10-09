import logging

import httpx
import pytest
from fastapi import FastAPI

from app.core.correlation import HEADER_NAME


async def test_generates_id_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    cid = response.headers[HEADER_NAME]
    assert len(cid) == 32
    int(cid, 16)  # hex


async def test_echoes_valid_incoming_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live", headers={HEADER_NAME: "req-123_abc.9"})
    assert response.headers[HEADER_NAME] == "req-123_abc.9"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "semi;colon", "new\tline", "<script>"])
async def test_replaces_malformed_incoming_id(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get("/health/live", headers={HEADER_NAME: bad})
    cid = response.headers[HEADER_NAME]
    assert cid != bad
    assert len(cid) == 32


async def test_each_request_gets_its_own_id(client: httpx.AsyncClient) -> None:
    first = (await client.get("/health/live")).headers[HEADER_NAME]
    second = (await client.get("/health/live")).headers[HEADER_NAME]
    assert first != second


async def test_id_is_attached_to_log_records(
    app: FastAPI, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.correlation import get_correlation_id

    seen: list[str | None] = []

    @app.get("/_probe")
    async def probe() -> dict[str, str]:
        seen.append(get_correlation_id())
        logging.getLogger("probe").warning("inside request")
        return {}

    with caplog.at_level(logging.WARNING):
        response = await client.get("/_probe", headers={HEADER_NAME: "trace-1"})
    assert seen == ["trace-1"]
    assert response.headers[HEADER_NAME] == "trace-1"
    assert get_correlation_id() is None  # context is reset after the request
