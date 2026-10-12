"""The one place that names vendors: builds the provider the orchestrator uses from settings."""

from app.ai.providers.anthropic_adapter import AnthropicProvider
from app.ai.providers.base import LlmProvider
from app.ai.providers.errors import LlmNotConfigured
from app.ai.providers.fake import FakeLlmProvider
from app.ai.providers.http import HttpxLlm
from app.ai.providers.openai_adapter import OpenAIProvider
from app.ai.providers.resilience import FallbackLlm, RetryingLlm
from app.core.config import Settings


def _one(kind: str, settings: Settings) -> LlmProvider:
    http = HttpxLlm(settings.ai_request_timeout_seconds)
    if kind == "fake":
        return FakeLlmProvider()
    if kind == "openai":
        if not settings.openai_api_key.get_secret_value() or not settings.ai_openai_model:
            raise LlmNotConfigured("openai needs OPENAI_API_KEY and AI_OPENAI_MODEL")
        return OpenAIProvider(settings.openai_api_key, settings.ai_openai_model, http)
    if kind == "anthropic":
        if not settings.anthropic_api_key.get_secret_value() or not settings.ai_anthropic_model:
            raise LlmNotConfigured("anthropic needs ANTHROPIC_API_KEY and AI_ANTHROPIC_MODEL")
        return AnthropicProvider(settings.anthropic_api_key, settings.ai_anthropic_model, http)
    raise LlmNotConfigured(f"unknown AI provider {kind!r}")


def build_llm(settings: Settings) -> LlmProvider:
    """The configured provider, retried once, with the optional fallback behind it. Raises
    `LlmNotConfigured` when a selected provider has no key or no model name."""
    chain: list[LlmProvider] = [RetryingLlm(_one(settings.ai_provider, settings))]
    fallback = settings.ai_fallback_provider
    if fallback and fallback != settings.ai_provider:
        chain.append(RetryingLlm(_one(fallback, settings)))
    return chain[0] if len(chain) == 1 else FallbackLlm(chain)
