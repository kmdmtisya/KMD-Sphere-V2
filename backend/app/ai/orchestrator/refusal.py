"""Questions the assistant declines before any model is asked (P10-T08.3).

These are requests the product must refuse whatever the model might say: executing trades, promising
returns, reading someone else's data, and revealing instructions or secrets. The rules are
deliberately narrow: they catch the plain request, while the tool allow-list, the server-side
scope and the answer checks hold even when a request is phrased to slip past them. A question that
only mentions these topics ("should I buy this ETF?", "is this return guaranteed?") is answered."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Refusal:
    category: str
    message: str


_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "trade_execution",
        "I can explain and compare, but I cannot place orders or move money. "
        "Trades must be made with your broker.",
        re.compile(
            r"\b(place|execute|submit|send|make|enter)\b.{0,25}"
            r"\b(an? )?(buy |sell |market |limit )?"
            r"(order|trade)s?\b|"
            r"\b(buy|sell)\b.{0,50}\b(for me|right now|immediately|automatically)\b|"
            r"\bauto-?trad\w*|\b(withdraw|transfer|wire)\b.{0,25}\b(money|funds|cash)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "guaranteed_returns",
        "I cannot guarantee or promise any return. I can show scenarios under stated "
        "assumptions, and they are illustrations, not promises.",
        re.compile(
            r"\b(guarantee|promise|assure)\s+(me|that|my)\b|\bguaranteed\s+(to|returns?|profits?|"
            r"gains?|income)\b|\b(sure|certain)\s+(thing|win|bet)\b|\bcan'?t\s+lose\b|"
            r"\brisk[- ]free\s+(way|method|trick)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "other_users_data",
        "I can only discuss your own accounts and data.",
        re.compile(
            r"\b(another|other|different|all|every)\s+users?\b|"
            r"\b(someone|somebody)\s+else'?s?\b.{0,30}\b(portfolio|account|holdings?|balance|"
            r"net worth|transactions?|goals?)\b|"
            r"\b(user|account|portfolio)\s*(id)?\s*[:#]?\s*[0-9a-f]{8}-[0-9a-f]{4}-",
            re.IGNORECASE,
        ),
    ),
    (
        "instructions_or_secrets",
        "I cannot share my instructions or any credentials or keys.",
        re.compile(
            r"\b(system|hidden|initial|developer)\s+(prompt|instructions?|message)\b|"
            r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|your)\b.{0,20}"
            r"\b(instructions?|rules|prompt)\b|"
            r"\b(reveal|show|print|tell me|give me|dump)\b.{0,30}\b(api[- ]?keys?|secrets?|"
            r"passwords?|tokens?|credentials?|connection string)\b|"
            r"\b(you are now|act as)\b.{0,30}\b(dan|unrestricted|jailbroken|developer mode)\b",
            re.IGNORECASE,
        ),
    ),
)


def check_question(question: str) -> Refusal | None:
    for category, message, pattern in _RULES:
        if pattern.search(question):
            return Refusal(category, message)
    return None
