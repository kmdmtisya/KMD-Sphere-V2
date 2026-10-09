import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.correlation import HEADER_NAME


class _Payload(BaseModel):
    amount: str
    currency: str


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["type"] == "https://wealthsphere.app/problems/not-found"
    assert body["correlation_id"] == response.headers[HEADER_NAME]


async def test_method_not_allowed_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.post("/health/live")
    assert response.status_code == 405
    assert response.json()["title"] == "Method Not Allowed"


async def test_validation_error_lists_fields_and_never_echoes_input(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    @app.post("/_validate")
    async def validate(payload: _Payload) -> dict[str, str]:
        return {"ok": payload.amount}

    response = await client.post(
        "/_validate", json={"amount": 12345, "currency": "SUPER-SECRET-VALUE"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Validation failed"
    assert any(e["field"] == "amount" for e in body["errors"])
    assert "SUPER-SECRET-VALUE" not in response.text
    assert "12345" not in response.text


async def test_unhandled_exception_is_generic_500_with_correlation_id(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    @app.get("/_boom")
    async def boom() -> None:
        raise RuntimeError("internal detail: db password is hunter2")

    response = await client.get("/_boom", headers={HEADER_NAME: "boom-1"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["correlation_id"] == "boom-1"
    assert response.headers[HEADER_NAME] == "boom-1"
    assert "hunter2" not in response.text
