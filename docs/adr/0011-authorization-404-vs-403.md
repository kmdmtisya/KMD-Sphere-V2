# ADR-0011: Authorization model and the 404-vs-403 policy

Status: Accepted (P04-T03, 2026-10-10; implements the authorization rules already approved in CLAUDE.md and docs/security.md)

## Context
Every WealthSphere resource that holds user data (portfolios, holdings, transactions, goals, risk profiles, AI conversations) must be reachable only by its owner. Insecure direct object references (IDOR), where a caller substitutes another user's id, are the most likely way to leak financial data. We also need a consistent answer for "not yours" that does not let a caller discover which ids exist.

## Decision
1. **Ownership is enforced in the query.** Repositories start every query for user data with `owned_by(Model, current_user.id)` (`app/core/authz.py`); updates and deletes repeat `user_id = :current_user` in their `WHERE` clause. Another user's row is never loaded, so a forgotten check cannot leak it.
2. **The owner is always the authenticated user.** Request bodies never carry `user_id`/owner fields (schemas use `extra="forbid"`); the server sets ownership from the token.
3. **404 for "does not exist" and for "not yours"**, with an identical body (`ResourceNotFoundError`). Callers cannot tell the two apart, so ids cannot be probed.
4. **403 only when the caller can see the resource but lacks a permission for the action** (`PermissionDeniedError`), for example a read-only member of a shared portfolio trying to edit it, or a missing role.
5. **401 for any authentication failure**, with one uniform body (P04-T02).
6. **Every id route has a cross-user test.** `tests/authz_harness.py` provides two users and `assert_hidden_from(...)`, which checks the 404 *and* that it is indistinguishable from a missing id. `tests/idor_registry.py` names the test for each route, and `tests/test_idor_coverage.py` fails the build if any route with an id in its path is not registered.

## Consequences
- New modules get ownership enforcement and IDOR tests by following one pattern; CI catches a route added without its test.
- Shared resources (portfolio members, P05) extend this with explicit membership in the query, and use 403 for role failures on resources the member can see.
- Support or admin access, if ever needed, is a separate, audited role path, never a bypass of `owned_by`.
