"""Development helpers for the local Keycloak realm (P04-T01). Standard library only.

    python scripts/keycloak_dev.py seed-users   # set dev passwords from .env, reset MFA enrolment
    python scripts/keycloak_dev.py smoke        # verify PKCE, rejected grants and TOTP enrolment

Reads KEYCLOAK_PORT, KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD and KEYCLOAK_TEST_USER_PASSWORD from
`.env` (git-ignored). Nothing secret is printed. For the local development stack only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import http.cookiejar
import json
import re
import secrets
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REALM = "wealthsphere"
CLIENT = "wealthsphere-mobile"
REDIRECT = "com.kmdmtisya.wealthsphere:/oauth2redirect"
USERS = ["alice@example.test", "bob@example.test", "mfa@example.test"]


def env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit(".env not found; copy .env.example and fill it in")
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


E = env()
BASE = f"http://127.0.0.1:{E.get('KEYCLOAK_PORT', '8081')}"
OIDC = f"{BASE}/realms/{REALM}/protocol/openid-connect"


def require(name: str) -> str:
    value = E.get(name, "")
    if not value or value == "CHANGE_ME":
        sys.exit(f"{name} is not set in .env")
    return value


# ------------------------------------------------------------------------ HTTP helpers
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # surface redirects to the caller


class _LocalhostSecurePolicy(http.cookiejar.DefaultCookiePolicy):
    """Browsers treat http://127.0.0.1 as a secure context and send `Secure` cookies to it;
    Python's cookie jar does not. Keycloak's login cookies are `Secure`, so allow them locally."""

    def return_ok_secure(self, cookie, request):
        return request.host.split(":")[0] in (
            "127.0.0.1",
            "localhost",
        ) or super().return_ok_secure(cookie, request)

    def set_ok(self, cookie, request):
        return (
            True
            if request.host.split(":")[0] in ("127.0.0.1", "localhost")
            else super().set_ok(cookie, request)
        )


def opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar(policy=_LocalhostSecurePolicy())
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), _NoRedirect()
    )


def call(
    op: urllib.request.OpenerDirector,
    url: str,
    data: dict | None = None,
    headers: dict | None = None,
    method: str | None = None,
):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        resp = op.open(req, timeout=20)
        return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def admin_token() -> str:
    status, _, body = call(
        opener(),
        f"{BASE}/realms/master/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": require("KEYCLOAK_ADMIN"),
            "password": require("KEYCLOAK_ADMIN_PASSWORD"),
        },
    )
    if status != 200:
        sys.exit(f"admin login failed ({status})")
    return json.loads(body)["access_token"]


def admin(method: str, path: str, token: str, payload: object | None = None):
    req = urllib.request.Request(
        f"{BASE}/admin/realms/{REALM}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
            return resp.status, json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def user_id(token: str, username: str) -> str:
    status, users = admin(
        "GET", f"/users?username={urllib.parse.quote(username)}&exact=true", token
    )
    if status != 200 or not users:
        sys.exit(f"user {username} not found; was the realm imported?")
    return users[0]["id"]


# ------------------------------------------------------------------------- seed users
def seed_users() -> None:
    password = require("KEYCLOAK_TEST_USER_PASSWORD")
    token = admin_token()
    for username in USERS:
        uid = user_id(token, username)
        status, body = admin(
            "PUT",
            f"/users/{uid}/reset-password",
            token,
            {"type": "password", "value": password, "temporary": False},
        )
        # The realm's password history rejects re-setting the same password: it is already set.
        if status == 400 and "PasswordHistory" in str(body):
            continue
        if status != 204:
            sys.exit(f"setting the password for {username} failed ({status})")
    # MFA user: drop any OTP credential and require enrolment again, so the smoke test can enrol.
    uid = user_id(token, "mfa@example.test")
    _, creds = admin("GET", f"/users/{uid}/credentials", token)
    for cred in creds or []:
        if cred.get("type") == "otp":
            admin("DELETE", f"/users/{uid}/credentials/{cred['id']}", token)
    _, user = admin("GET", f"/users/{uid}", token)
    user["requiredActions"] = ["CONFIGURE_TOTP"]
    admin("PUT", f"/users/{uid}", token, user)
    print(f"seeded {len(USERS)} users; mfa@example.test must enrol TOTP on next login")


# ------------------------------------------------------------------------------- smoke
def totp(raw_secret: str, at: float | None = None) -> str:
    """RFC 6238 code for Keycloak's raw TOTP secret (the hidden `totpSecret` form value; the
    Base32 text shown to people encodes the same bytes)."""
    key = raw_secret.encode()
    counter = int((at or time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    ) % 1_000_000
    return f"{code:06d}"


def form_action(page: str) -> str:
    match = re.search(r'<form[^>]*action="([^"]+)"', page)
    if not match:
        raise AssertionError("no form on the page")
    return html.unescape(match.group(1))


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def auth_url(challenge: str | None, response_type: str = "code") -> str:
    params = {
        "client_id": CLIENT,
        "response_type": response_type,
        "scope": "openid",
        "redirect_uri": REDIRECT,
        "state": secrets.token_hex(8),
        "nonce": secrets.token_hex(8),
    }
    if challenge:
        params |= {"code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{OIDC}/auth?{urllib.parse.urlencode(params)}"


def code_from(headers: dict) -> str:
    location = headers.get("Location", "")
    assert location.startswith(REDIRECT), (
        f"expected redirect to the app, got {location[:80]}"
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    assert "code" in query, f"no code in redirect: {query}"
    return query["code"][0]


def login(
    username: str, password: str, otp_secret: list[str] | None = None
) -> tuple[str, str]:
    """Runs the browser login and returns (code, verifier). Handles TOTP enrolment and OTP prompts."""
    op = opener()
    verifier, challenge = pkce()
    status, headers, page = call(op, auth_url(challenge))
    assert status == 200, f"login page {status}"
    status, headers, page = call(
        op, form_action(page), {"username": username, "password": password}
    )
    for _ in range(6):
        if status in (302, 303):
            location = headers.get("Location", "")
            if location.startswith(REDIRECT):
                return code_from(headers), verifier
            status, headers, page = call(
                op, location
            )  # a step inside the realm (e.g. enrolment)
            continue
        if 'name="totpSecret"' in page:  # enrolment page
            secret = re.search(r'name="totpSecret" value="([^"]+)"', page).group(1)
            if otp_secret is not None:
                otp_secret.append(secret)
            status, headers, page = call(
                op,
                form_action(page),
                {
                    "totp": totp(secret),
                    "totpSecret": secret,
                    "userLabel": "smoke",
                    "mode": "manual",
                },
            )
        elif 'name="otp"' in page:  # OTP prompt
            assert otp_secret, "OTP requested but no secret known"
            status, headers, page = call(
                op, form_action(page), {"otp": totp(otp_secret[0])}
            )
        else:
            raise AssertionError(
                f"unexpected page (status {status}): {re.sub(r'<[^>]+>', ' ', page)[:200]}"
            )
    raise AssertionError("login did not complete")


def exchange(code: str, verifier: str | None) -> tuple[int, dict]:
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT,
        "code": code,
        "redirect_uri": REDIRECT,
    }
    if verifier:
        data["code_verifier"] = verifier
    status, _, body = call(opener(), f"{OIDC}/token", data)
    return status, json.loads(body)


def claims(jwt: str) -> dict:
    payload = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def smoke() -> None:
    password = require("KEYCLOAK_TEST_USER_PASSWORD")
    results: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        results.append((name, ok))
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    # 1. Authorization Code + PKCE succeeds and the token targets the API.
    code, verifier = login("alice@example.test", password)
    status, tokens = exchange(code, verifier)
    check(
        "authorization code + PKCE returns tokens",
        status == 200 and "access_token" in tokens and "refresh_token" in tokens,
    )
    c = claims(tokens.get("access_token", "a.e30.b"))
    aud = c.get("aud", [])
    check(
        "access token audience includes wealthsphere-api",
        "wealthsphere-api" in (aud if isinstance(aud, list) else [aud]),
    )
    check("access token issued to the mobile client", c.get("azp") == CLIENT)
    check(
        "access token lifetime is 5 minutes", c.get("exp", 0) - c.get("iat", 0) == 300
    )

    # 2. The code cannot be redeemed without the verifier (PKCE enforced).
    code, _ = login("bob@example.test", password)
    status, body = exchange(code, None)
    check(
        "token exchange without code_verifier is rejected",
        status == 400 and body.get("error") == "invalid_grant",
    )

    # 3. A request without a PKCE challenge is refused.
    status, headers, page = call(opener(), auth_url(None))
    location = headers.get("Location", "")
    check(
        "authorization request without PKCE is refused",
        (status in (302, 303) and "error=" in location) or status == 400,
    )

    # 4. Implicit and password grants are disabled.
    status, headers, page = call(opener(), auth_url(pkce()[1], response_type="token"))
    location = headers.get("Location", "")
    check(
        "implicit flow is refused",
        (status in (302, 303) and "error=" in location) or status == 400,
    )
    status, _, body = call(
        opener(),
        f"{OIDC}/token",
        {
            "grant_type": "password",
            "client_id": CLIENT,
            "username": "alice@example.test",
            "password": password,
        },
    )
    check(
        "password grant is refused",
        status in (400, 401)
        and json.loads(body).get("error") in ("unauthorized_client", "invalid_client"),
    )

    # 5. MFA: enrolment, then a later login requires the TOTP code.
    secret: list[str] = []
    code, verifier = login("mfa@example.test", password, otp_secret=secret)
    check(
        "TOTP enrolment completes and signs in",
        bool(secret) and exchange(code, verifier)[0] == 200,
    )
    time.sleep(31 - time.time() % 30)  # a fresh 30-second window: codes are single-use
    op = opener()
    verifier, challenge = pkce()
    _, _, page = call(op, auth_url(challenge))
    status, headers, page = call(
        op, form_action(page), {"username": "mfa@example.test", "password": password}
    )
    check("a later login asks for the TOTP code", 'name="otp"' in page)
    status, headers, page = call(
        op,
        form_action(page),
        {"otp": "000000" if totp(secret[0]) != "000000" else "111111"},
    )
    check("a wrong TOTP code is rejected", status == 200 and 'name="otp"' in page)
    status, headers, page = call(op, form_action(page), {"otp": totp(secret[0])})
    check(
        "login with the right TOTP code succeeds",
        status in (302, 303) and exchange(code_from(headers), verifier)[0] == 200,
    )

    # 6. Realm settings as imported.
    token = admin_token()
    _, realm = admin("GET", "", token)
    check(
        "password policy is set (length 12, mixed, history)",
        "length(12)" in realm.get("passwordPolicy", "")
        and "passwordHistory(5)" in realm.get("passwordPolicy", ""),
    )
    check(
        "email verification is required for new accounts",
        realm.get("verifyEmail") is True,
    )
    _, clients = admin("GET", f"/clients?clientId={CLIENT}", token)
    cl = clients[0]
    check(
        "mobile client is public with standard flow only",
        cl["publicClient"]
        and cl["standardFlowEnabled"]
        and not cl["implicitFlowEnabled"]
        and not cl["directAccessGrantsEnabled"],
    )

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    commands = {"seed-users": seed_users, "smoke": smoke}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
