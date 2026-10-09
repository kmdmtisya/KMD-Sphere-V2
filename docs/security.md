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
| Audit | Append-only audit events for financial changes and AI/tool activity | P04-T04 |
| Secrets | Never in source control; `.env` is git-ignored; secret manager in cloud; CI uses OIDC, not long-lived keys | P01-T05, P13-T06 |
| Transport / storage | TLS 1.2+ (prefer 1.3); encryption at rest | P13 |
| Logging | No secrets or unnecessary financial payloads in logs; redaction filter with tests | P01-T12 |
| Supply chain | Secret scanning, dependency and container scanning, SAST, SBOM | P01-T11 |
| Backups | Encrypted backups, restore tests, documented RPO/RTO | P13-T10 |
| Privacy | Consent, retention, export and account deletion | P14-T05 |
| Reviews | OWASP API Security Top 10, OWASP MASVS, penetration test | P14 |

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
