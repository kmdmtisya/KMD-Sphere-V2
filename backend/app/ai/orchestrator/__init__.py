"""The AI orchestrator (P10-T06): the only place that talks to both the model and the tools.

`User -> Orchestrator -> authorization -> allow-listed tool -> deterministic result -> LLM ->
validated response` (docs/ai-governance.md)."""
