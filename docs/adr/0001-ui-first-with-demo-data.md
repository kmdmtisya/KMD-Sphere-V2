# ADR-0001: UI first with DEMO data

Status: Accepted (user approval, 2026-10-09)

## Context
CLAUDE.md orders work backend-first (identity, schema, portfolio) and says not to start with the AI recommendation interface. The approved UI/UX specification defines delivery gates that build the first screens on mock data with an explicit `DEMO` indicator.

## Decision
Run two lanes in parallel after the foundation: a mobile lane (design system, then screens on typed demo fixtures) and a backend lane (identity, portfolio core, analytics). They join in P09.

Demo data is accessed only through repository interfaces that mirror the planned `/api/v1` endpoints, so replacing demo with live implementations touches no screen code. Every screen showing fixtures shows a `DemoBadge`, and release builds cannot select demo mode. The AI recommendation UI is built last, on live, evidence-backed services.

## Consequences
- Early, reviewable UI without waiting for the backend. The risk of DTO drift is controlled by P05-T10 (contract reconciliation).
- Flutter never computes financial truth: demo forecasts are canned responses until the backend engine (P06) is wired in (P09-T03).
