"""LLM providers behind one interface (P10-T05, ADR-0017). Consumers import `base`, `models`,
`errors`, `resilience` and `registry` only; the vendor adapters and the fake are wired in at one
composition point (`registry.py`)."""
