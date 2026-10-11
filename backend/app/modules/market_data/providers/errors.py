"""Provider failures. Only some are worth retrying or count against a provider's health."""

from datetime import timedelta


class ProviderError(Exception):
    """Base of every provider failure."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached or answered with a server error. Retryable; counts
    against the provider's health."""


class RateLimited(ProviderUnavailable):
    """The provider refused the call because a quota was reached. Retryable after `retry_after`
    (when it said how long)."""

    def __init__(self, message: str = "rate limited", retry_after: timedelta | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAuthError(ProviderUnavailable):
    """The provider refused our credentials (a missing, wrong or revoked key, or a plan that does
    not include the call). Not retried (asking again changes nothing) but it does count against
    the provider's health and lets a fallback chain move on. The message never contains the key."""


class CircuitOpen(ProviderUnavailable):
    """The call was not made because the provider has failed repeatedly and is being left alone."""


class AllProvidersFailed(ProviderUnavailable):
    """Every provider in a fallback chain failed."""

    def __init__(self, errors: list[ProviderError]) -> None:
        super().__init__(f"all {len(errors)} providers failed")
        self.errors = errors


class SymbolNotFound(ProviderError):
    """The provider does not know this instrument. Not retryable; says nothing about health."""


class UnsupportedKind(ProviderError):
    """The provider does not serve this kind of asset. Not retryable; says nothing about health."""


class ProviderDataError(ProviderError):
    """The provider answered with data that failed validation (a non-positive price, a naive
    timestamp, ...). Never stored. Not retried: asking again returns the same bad data."""
