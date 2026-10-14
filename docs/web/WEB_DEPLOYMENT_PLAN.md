# WealthSphere Web Portal: CI/CD and deployment plan

**Status:** Proposed (2026-10-14).
- **Nothing is provisioned.** Hosting follows the cloud decision (DEC-02, P15-T01), and no paid infrastructure is created without approval.
- **Deployment work is planned, not built yet.** It lands in P14-T21 and P14-T22, on the P15 pipeline.

## 1. Build and test pipeline (P14-T21, GitHub Actions)

A new workflow, `.github/workflows/web.yml`, runs on every pull request that touches `web/`, `design/tokens/` or `backend/openapi.json`. It ends in one required check, **`web gate`**, like the existing `backend gate` and `mobile gate`.

| Step | Tool | Fails the build when |
|---|---|---|
| Install | `npm ci` with the lockfile; Node LTS pinned | the lockfile is out of date |
| Format and lint | Prettier, ESLint (including the no-money-arithmetic and no-colour-literal rules) | any finding |
| Type check | `tsc --noEmit` (strict) | any error |
| Contract | regenerate the OpenAPI client and compare it with the committed one | the client is out of date |
| Tokens | regenerate the CSS variables and Dart palette from `design/tokens` and compare them | out of date |
| Unit and component | Vitest and Testing Library, with axe on components | a failure or a serious accessibility violation |
| End to end | Playwright (Chromium, Firefox, WebKit) against `backend/tests/e2e_server.py` plus the BFF | a journey fails |
| Accessibility and performance | Lighthouse CI on the tested pages, with budgets (DEC-36) | below budget |
| Security | `npm audit` (high or above), licence allow-list, gitleaks (already in the `security gate`), CSP check | any finding |
| Build | `next build` in standalone mode and a container image (distroless or slim Node) | build error |

**Adding `web gate` to the `main` ruleset** needs repository-admin rights. The user does this when P14-T21 is reached (the same as for the existing required checks); until then the workflow runs but does not block merging.

## 2. Runtime topology

```text
Browser ──HTTPS──► CDN (static assets, immutable hashes) ─┐
        ──HTTPS──► Load balancer / ingress ──► web (Next.js standalone: pages + BFF) ──► api (FastAPI)
                                                    │                                      │
                                                    └──► Redis (sessions, encrypted)       └──► PostgreSQL, Redis, workers
Keycloak ◄── OIDC redirects ── browser / BFF
```

- **Web container.** One stateless Next.js container per environment, horizontally scalable: sessions are in Redis, not in the container. It runs on the same managed container platform as the API (for example AWS ECS Fargate, Google Cloud Run or OCI Container Instances, whichever DEC-02 chooses).
- **Static assets.** Served through the CDN with content-hashed names, cached for a long time. HTML is not cached at the edge, because it is per user.
- **Origins.** One origin for the portal (for example `app.<domain>`) and the existing API origin. The browser talks only to the portal origin; the BFF reaches the API on the private network. No CORS opening is needed.
- **Secrets.** These live in the cloud secret store, read at start:
  - the OIDC client secret;
  - the session-encryption key;
  - the Redis credentials.

  None is in the repository or the image (the gitleaks gate already applies).

## 3. Environments and configuration

| Setting | Local | Staging | Production |
|---|---|---|---|
| `WEB_BASE_URL` | `http://localhost:3000` | `https://app.staging.<domain>` | `https://app.<domain>` |
| `API_INTERNAL_URL` | `http://127.0.0.1:8000` | private service URL | private service URL |
| `OIDC_ISSUER` | the local Keycloak realm | staging realm | production realm |
| `OIDC_CLIENT_ID` | `wealthsphere-web` | the same | the same |
| `OIDC_CLIENT_SECRET` | `.env` (dev only) | secret store | secret store |
| `SESSION_KEY` | `.env` (dev only) | secret store | secret store |
| `REDIS_URL` | compose Redis | managed Redis | managed Redis |
| Keycloak redirect URIs | `http://localhost:3000/api/auth/callback` | the staging URL only | the production URL only |

Configuration is validated at start (missing or insecure values stop the container, as `Settings` does for the API). Production refuses `http://` URLs and development secrets.

## 4. Release flow

1. Merge to `main` (all required checks green), then the image is built and tagged with the commit SHA (immutable) and an SBOM is produced.
2. Deploy to staging automatically. Then run the smoke tests (the P15-T11 suite gains web journeys):
   - sign in with the staging test user and MFA;
   - dashboard figures equal the API's;
   - a currency switch;
   - a copilot round trip;
   - sign out.
3. Production needs an approval (GitHub environment protection with the user as reviewer) that names the SHA. The rollout is blue/green or a rolling revision with health checks.
4. Post-deployment smoke tests run against production with a synthetic account, then the release is recorded in `EXECUTION_LOG.md`.
5. **Rollback.** Redeploy the previous image tag (the previous revision is kept warm for at least 24 hours). Web releases never include database migrations; any backend change ships through the API pipeline first, backward compatible.

## 5. Domain, DNS, TLS and headers

- **DNS.** One record per environment for the portal, at the registrar or the DNS service chosen with DEC-02.
- **TLS.** Managed certificates on the load balancer and CDN, TLS 1.2 or later. HSTS with `includeSubDomains` once all subdomains are HTTPS.
- **Security headers.** Strict CSP with nonces, `frame-ancestors 'none'`, nosniff, `Referrer-Policy: no-referrer`, a `Permissions-Policy` that denies everything unused. Checked by the CSP step in CI and by the staging smoke tests.

## 6. Monitoring

- **Logs.** BFF access logs carry the correlation ID and no bodies, tokens or amounts.
- **Metrics.** Requests, latency, upstream errors, sign-in outcomes and the session count.
- **Real-user monitoring.** Web vitals are sampled from real users.
- **Alerts.** On the BFF 5xx rate, sign-in failure spikes, the upstream API error rate, and an LCP p75 regression.
- **Front-end errors.** Sent to the same telemetry stack (P15) through a BFF endpoint, scrubbed of personal data.

## 7. Hosting cost assumptions (to confirm with DEC-02)

These are list-price orders of magnitude for planning, not quotes:

| Item | Assumption |
|---|---|
| Web container | One small instance (0.5 vCPU, 1 GB) per environment, autoscaling to 3 in production; roughly tens of US dollars a month per environment at low traffic |
| CDN | Static assets only; low single-digit dollars a month at launch traffic |
| Redis (sessions) | The existing managed Redis, with a separate database or keyspace; no new instance unless sizing says so |
| Load balancer and TLS | Shared with the API |

The budget is set and approved with DEC-02 and P15-T01, and nothing is bought before that approval.
