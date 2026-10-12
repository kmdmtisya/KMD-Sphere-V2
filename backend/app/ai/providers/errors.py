"""LLM provider failures. Messages name the provider and the cause class, never the key, the
request, the prompt or the response body."""


class LlmError(Exception):
    """Base of every provider failure."""


class LlmUnavailable(LlmError):
    """The provider could not be reached or answered with a server error. Retryable."""


class LlmRateLimited(LlmUnavailable):
    """Quota or rate limit reached. Retryable after a pause."""


class LlmAuthError(LlmUnavailable):
    """The provider refused our credentials (missing, wrong or revoked key). Not retried; a
    fallback provider may still answer."""


class LlmBadRequest(LlmError):
    """The provider rejected the request as malformed or too large. Retrying the same request
    changes nothing."""


class LlmInvalidOutput(LlmError):
    """The provider answered with something that is not the expected shape (unparseable tool
    arguments, no content). The orchestrator may retry once, then refuses."""


class LlmNotConfigured(LlmError):
    """No provider is configured (no key or no model name for the selected provider)."""
