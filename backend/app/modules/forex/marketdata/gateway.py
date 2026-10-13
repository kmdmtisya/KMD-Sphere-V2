"""The fan-out gateway (P13-T02.4, design section 4.3). The backend holds one upstream
subscription per provider; each app connection subscribes here to the pairs it shows.

Per-user limits: at most `max_connections` open sockets per user and `max_instruments` pairs per
socket. Updates are coalesced per pair (a slow client gets the latest price, not a backlog), so a
socket's memory is bounded by its pair count. Only quotes that are not suspect are published, and
the last good quote of each pair is kept, with its own time, for a new subscriber's snapshot."""

import asyncio

from app.modules.forex.marketdata.types import FeedStatus, Quality, ReceivedQuote


class LimitExceeded(Exception):
    def __init__(self, what: str) -> None:
        super().__init__(f"too many {what}")
        self.what = what


class Subscriber:
    def __init__(self, subject: str) -> None:
        self.subject = subject
        self.instruments: set[str] = set()
        self._quotes: dict[str, ReceivedQuote] = {}
        self._statuses: dict[str, FeedStatus] = {}
        self._ready = asyncio.Event()

    def push_quote(self, quote: ReceivedQuote) -> None:
        if quote.quote.instrument in self.instruments:
            self._quotes[quote.quote.instrument] = quote
            self._ready.set()

    def push_status(self, provider: str, status: FeedStatus) -> None:
        self._statuses[provider] = status
        self._ready.set()

    async def drain(self, wait_seconds: float) -> tuple[list[ReceivedQuote], dict[str, FeedStatus]]:
        """What arrived since the last call, waiting up to `wait_seconds` for something."""
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), wait_seconds)
            except TimeoutError:
                return [], {}
        self._ready.clear()
        quotes = [q for i, q in sorted(self._quotes.items()) if i in self.instruments]
        statuses = self._statuses
        self._quotes, self._statuses = {}, {}
        return quotes, statuses


class QuoteHub:
    def __init__(self, max_connections: int = 3, max_instruments: int = 20) -> None:
        if max_connections < 1 or max_instruments < 1:
            raise ValueError("limits must be at least 1")
        self.max_connections = max_connections
        self.max_instruments = max_instruments
        self._subscribers: dict[str, set[Subscriber]] = {}
        self.last_good: dict[str, ReceivedQuote] = {}
        self.feed_status: dict[str, FeedStatus] = {}

    @property
    def connections(self) -> int:
        return sum(len(s) for s in self._subscribers.values())

    def open(self, subject: str) -> Subscriber:
        mine = self._subscribers.setdefault(subject, set())
        if len(mine) >= self.max_connections:
            raise LimitExceeded("connections")
        subscriber = Subscriber(subject)
        mine.add(subscriber)
        return subscriber

    def close(self, subscriber: Subscriber) -> None:
        mine = self._subscribers.get(subscriber.subject)
        if mine is not None:
            mine.discard(subscriber)
            if not mine:
                del self._subscribers[subscriber.subject]

    def subscribe(
        self, subscriber: Subscriber, instruments: list[str], known: set[str]
    ) -> list[ReceivedQuote]:
        """Adds pairs to a socket. Returns the last good quote of each (for the snapshot)."""
        unknown = sorted(set(instruments) - known)
        if unknown:
            raise ValueError("unknown instrument")
        wanted = subscriber.instruments | set(instruments)
        if len(wanted) > self.max_instruments:
            raise LimitExceeded("instruments")
        subscriber.instruments = wanted
        return [self.last_good[i] for i in sorted(set(instruments)) if i in self.last_good]

    def unsubscribe(self, subscriber: Subscriber, instruments: list[str]) -> None:
        subscriber.instruments -= set(instruments)

    def publish(self, quote: ReceivedQuote) -> None:
        if quote.quality is Quality.SUSPECT:
            return
        self.last_good[quote.quote.instrument] = quote
        for mine in self._subscribers.values():
            for subscriber in mine:
                subscriber.push_quote(quote)

    def publish_status(self, provider: str, status: FeedStatus) -> None:
        self.feed_status[provider] = status
        for mine in self._subscribers.values():
            for subscriber in mine:
                subscriber.push_status(provider, status)
