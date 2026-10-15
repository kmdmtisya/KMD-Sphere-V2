# WealthSphere web portal

The desktop web channel of WealthSphere (phase P14, [ADR-0018](../docs/adr/0018-web-portal-architecture.md)): Next.js (App Router), React and TypeScript, with a Backend-for-Frontend (BFF) in the same server. Read [docs/web](../docs/web) before changing anything here.

**Rules that are checked in CI**
- **No financial logic.** The backend is authoritative. The web shows the decimal strings the API sends and never calculates money; `wealthsphere/no-money-arithmetic` enforces this (QG-26.3).
- **Colours only from tokens.** `wealthsphere/no-colour-literals` and `scripts/check-css-colours.mjs` reject colour literals outside `src/tokens`, so Light, Dark and System apply everywhere ([WEB_THEME_SYSTEM.md](../docs/web/WEB_THEME_SYSTEM.md)).
- **No tokens in the browser.** Access and refresh tokens stay on the server (BFF, from P14-T05). The proxy forwards only allow-listed `/api/v1/*` paths.
- **The API contract is generated.** `src/lib/api/schema.d.ts` comes from `backend/openapi.json`; CI fails on drift.

## Commands

| Command | What it does |
|---|---|
| `npm ci` | Install the locked dependencies (Node 20.9 or newer; CI uses Node 24) |
| `npm run dev` | Development server on http://localhost:3000 |
| `npm run lint` | ESLint (Next.js rules and the WealthSphere guards) and the CSS colour check |
| `npm run lint:selftest` | Proves the guards fire on the seeded violations in `lint-fixtures/` |
| `npm run typecheck` | Route types (`next typegen`) and `tsc --noEmit` |
| `npm test` | Unit tests (Vitest) |
| `npm run api:generate` / `api:check` | Regenerate the API client / fail if it drifted from `backend/openapi.json` |
| `npm run build` | Production build (standalone output for the container) |
| `npm run start:standalone -- --port 3100` | Run the production build the way the container does |
| `npm run e2e` | Playwright against the standalone server |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `WS_API_BASE_URL` | `http://127.0.0.1:8000` | The API the BFF calls server to server. https, or http to a loopback address only |
| `WS_E2E_EXPECT_API` | unset | `1` makes the e2e health test require the API (set in CI, where the seeded backend runs) |
| `WS_PLAYWRIGHT_CHANNEL` | unset | `chrome` uses an installed Google Chrome when Playwright cannot download its own browser |

No secret is needed yet. The OIDC client secret and the session key arrive with P14-T05 and live only in the secret store, never in this repository.
