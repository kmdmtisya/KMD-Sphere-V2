"""FastAPI dependencies for authentication. Every protected route depends on `current_user`."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import AuthenticationError, TokenVerifier
from app.core.ratelimit import enforce_user_limit
from app.db.session import get_session
from app.modules.identity.service import CurrentUser, IdentityService, UserDisabledError

bearer = HTTPBearer(auto_error=False, description="OIDC access token from the WealthSphere realm")


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError("missing bearer token")
    verifier: TokenVerifier | None = request.app.state.token_verifier
    if verifier is None:
        raise AuthenticationError("authentication is not configured")
    # Fetching signing keys may do blocking HTTP: keep it off the event loop.
    claims = await run_in_threadpool(verifier.verify, credentials.credentials)
    await enforce_user_limit(request, f"{claims.issuer}|{claims.subject}")
    try:
        return await IdentityService(session).provision(claims)
    except UserDisabledError as e:
        raise AuthenticationError("account disabled") from e


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
