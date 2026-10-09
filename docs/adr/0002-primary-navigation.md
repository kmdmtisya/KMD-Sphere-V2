# ADR-0002: Primary navigation

Status: Proposed

## Context
The written specification defines the tabs Home, Portfolio, AI Wealth, Goals, More. The concept board shows Home, Portfolio, Invest, AI, More. The board is explicitly a visual direction, not a source of truth.

## Decision
Follow the written specification: **Home | Portfolio | AI Wealth | Goals | More**, implemented with GoRouter `StatefulShellRoute.indexedStack` so each tab keeps its own stack.

- Holdings are reached from Portfolio; the calculator lives under More.
- Contextual AI opens via `/ai?scope=portfolio:<id>`, `forecast:<id>` or `goal:<id>`.

## Consequences
Tab state is stable, re-tapping the active tab pops to its root, and Android back and iOS swipe-back follow platform conventions. Any later change to the tab set needs a new ADR.
