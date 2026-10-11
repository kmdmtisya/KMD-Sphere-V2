"""Market-data provider abstraction (P08-T02, ADR-0014).

Consumers import only from `base`, `models`, `resilience` and `registry`; vendor adapters and the
fake provider are wired in at composition time and never imported by feature code."""
