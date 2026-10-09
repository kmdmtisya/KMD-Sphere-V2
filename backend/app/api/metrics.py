"""Prometheus metrics endpoint. Internal only: disabled unless METRICS_TOKEN is configured, and
then protected by a bearer token. It is excluded from the public OpenAPI contract."""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST

router = APIRouter(include_in_schema=False)


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    token = request.app.state.settings.metrics_token.get_secret_value()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
        raise HTTPException(
            status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"}
        )
    return Response(request.app.state.telemetry.render_metrics(), media_type=CONTENT_TYPE_LATEST)
