# Operator views (P14-T17, DEC-34)

## Scope decision

Recorded under the user's advance approval of P14-T17 (2026-10-15); to be confirmed on review.

**What exists:** two read-only views for the `support` realm role.

| View | Endpoint | Shows |
|---|---|---|
| Platform status | `GET /api/v1/operator/status` | Dependency checks (database, Redis), environment, which optional modules are on (forex, forex feed, assistant provider, rate limits), account counts by status, and for the last 24 hours: audit events by outcome, the ten most frequent actions, background jobs by status, failed jobs by job name |
| Audit trail | `GET /api/v1/operator/audit?limit=&outcome=&action_prefix=` | The newest audit events: time, action, outcome, kind of actor, kind of resource, channel, correlation id |

**What an operator can never see through these views:** a user's portfolios, transactions, balances, goals or any other financial data; email addresses, names, user ids or subjects; resource ids; tokens; the details of an audit event (which are sanitised but are not shown at all); who performed an action. There are no write operations: no disabling accounts, no impersonation, no data edits. Anything of that kind would need its own decision.

**Who holds the role:** the `support` realm role is never a default role and is granted by an identity administrator in Keycloak. In the development realm, one demo account (`ops@example.test`) has it, and a test pins that it is the only one.

## Enforcement

- The API decides. `require_support` verifies the bearer token and requires `support` in its realm roles; otherwise 403. Role claims in headers or query strings are ignored.
- The web hides the menu entry and redirects the page for users without the role, but that is a convenience, not the control (QG-29.4).
- Audit: each successful view writes `operator.status.viewed` or `operator.audit.viewed` (the audit view records its filters), and each refused attempt writes `operator.access.denied` with outcome `denied`.

## Not in scope (recorded so it is a choice, not an omission)

User lookup or support-on-behalf-of access, account actions, data exports for operators, feed or job control, and alert routing. If support needs any of these, the scope decision is reopened.
