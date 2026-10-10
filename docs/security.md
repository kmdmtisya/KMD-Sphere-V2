# Security Requirements and Controls

Derived from CLAUDE.md (Security Rules), `SOLUTION_INTENT.md` section 23 and the implementation guide section 12. The threat model is produced in P04-T09.

## Principles
- Cross-user portfolio access is a critical security failure.
- Authorization is enforced server-side on every protected resource; the client is never trusted.
- Security controls are never weakened to fix an error.

## Controls

| Area | Requirement | Planned in |
|---|---|---|
| Identity | Keycloak, OIDC Authorization Code + PKCE, MFA, email verification, password policy | P04-T01 |
| Tokens | Short-lived access tokens, refresh rotation; stored only in secure mobile storage | P04-T06 |
| App access | Biometric unlock, lock on background/timeout | P04-T07 |
| Authorization | Ownership checks on every resource; IDOR tests per endpoint | P04-T03, P05-T09 |
| API protection | Rate limiting, brute-force controls, input limits, security headers | P04-T05 |
| Audit | Append-only audit events for financial changes and AI/tool activity (see "Audit events" below) | P04-T04 |
| Secrets | Never in source control; `.env` is git-ignored; secret manager in cloud; CI uses OIDC, not long-lived keys | P01-T05, P14-T06 |
| Transport / storage | TLS 1.2+ (prefer 1.3); encryption at rest | P14 |
| Logging | No secrets or unnecessary financial payloads in logs; redaction filter with tests | P01-T12 |
| Supply chain | Secret scanning, dependency and container scanning, SAST, SBOM | P01-T11 |
| Backups | Encrypted backups, restore tests, documented RPO/RTO | P14-T10 |
| Privacy | Consent, retention, export and account deletion | P15-T05 |
| Reviews | OWASP API Security Top 10, OWASP MASVS, penetration test | P15 |

## Secrets handling (current)
- Local development values live in `.env` (ignored by git); only `.env.example` with placeholders is committed.
- Provider and LLM keys are read from the environment or a secret manager, never from code, and never logged.

## Data classification
| Class | Examples | Handling |
|---|---|---|
| Restricted | credentials, tokens, API keys | secret storage only; never logged |
| Confidential | holdings, balances, transactions, goals | authorised access only; minimal logging; encrypted at rest |
| Internal | aggregated non-identifying metrics | access controlled |
| Public | marketing content, published disclosures | none |

## Reporting
Security issues: see `SECURITY.md` (added in P01-T11).

## Authorization and IDOR tests (ADR-0011)

- Query user data only through `owned_by(Model, user.id)` from `app/core/authz.py`; repeat `user_id = :user` in every `UPDATE`/`DELETE`.
- A resource that is not the caller's answers **404**, identical to a missing one; **403** is only for a visible resource and a missing permission.
- Never accept an owner or `user_id` in a request body.
- For every route with an id in its path, write a cross-user test with `tests/authz_harness.py`:

```python
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401

async def test_bob_cannot_read_alices_goal(http, two_users: TwoUsers) -> None:
    goal = await http.post("/api/v1/goals", headers=two_users.alice.headers, json={...})
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/goals/{goal.json()['id']}")
```

  then register it in `tests/idor_registry.py`. `tests/test_idor_coverage.py` fails CI for any id route without a registered test.

## Audit events (P04-T04)

Material financial changes, security-relevant changes and AI tool activity emit an audit event through `AuditWriter` in `app/core/audit.py`:

```python
await AuditWriter(session).record(
    "portfolio.transaction.created",          # <module>.<resource>.<verb>, lower-case
    Actor.user(user.id),                       # Actor.ai(user.id) for AI tool calls, Actor.system() for jobs
    resource_type="transaction",
    resource_id=tx.id,
    details={"changed": ["quantity"]},         # redacted before storage
)
await session.commit()                         # the change and its event commit together
```

- **Append-only.** The database rejects `UPDATE`, `DELETE` and `TRUNCATE` on `audit_events` (triggers in migration 0003); the ORM refuses to flush a change to or deletion of a loaded event; the writer has no update or delete method.
- **Same transaction.** Record the event before `commit()`; if the event cannot be written the change is rolled back too.
- **Correlation.** Each event stores the request's correlation ID (`X-Correlation-ID`), linking it to logs and traces.
- **Redaction.** `details` pass through `app.core.redaction.redact`: credentials, tokens and financial values (amounts, prices, balances and so on) are replaced with `[REDACTED]`; floats are never stored; details over 8 KiB are reduced to their key names. Store field names and resource ids, not amounts; the resource's own append-only history holds the values.
- **AI tool calls** store `hash_arguments(arguments)`, not the arguments (docs/ai-governance.md).
- **No foreign key to users**, so the trail outlives the rows it describes. Retention and account-deletion handling are defined in P15-T05 (privacy: export, deletion, retention). In deployed environments the application database role should not own `audit_events` (P15 hardening), so it cannot disable the triggers.
