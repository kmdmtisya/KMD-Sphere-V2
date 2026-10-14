"""The indicators an API caller may ask for, with bounded parameters (P13-T03).

A request names indicators as `name` or `name:p1,p2,...` (for example `rsi:14`, `macd:12,26,9`,
`bollinger:20,2`). Unknown names, wrong parameter counts and out-of-range values are refused, so
a caller cannot request unbounded work."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.errors import InvalidValueError
from app.modules.forex.analysis import indicators as ind

Series = list[Decimal | None]
MAX_PERIOD = 500


@dataclass(frozen=True)
class Bars:
    high: Sequence[Decimal]
    low: Sequence[Decimal]
    close: Sequence[Decimal]


@dataclass(frozen=True)
class Spec:
    name: str
    defaults: tuple[Decimal, ...]
    outputs: tuple[str, ...]
    run: Callable[[Bars, tuple[Decimal, ...]], dict[str, Series]]
    warmup: Callable[[tuple[int, ...]], int]  # index of the first value that exists


def _i(p: tuple[Decimal, ...]) -> tuple[int, ...]:
    return tuple(int(x) for x in p)


SPECS: dict[str, Spec] = {
    "sma": Spec(
        "sma",
        (Decimal(20),),
        ("value",),
        lambda b, p: {"value": ind.sma(b.close, _i(p)[0])},
        lambda p: p[0] - 1,
    ),
    "ema": Spec(
        "ema",
        (Decimal(20),),
        ("value",),
        lambda b, p: {"value": ind.ema(b.close, _i(p)[0])},
        lambda p: p[0] - 1,
    ),
    "macd": Spec(
        "macd",
        (Decimal(12), Decimal(26), Decimal(9)),
        ("macd", "signal", "histogram"),
        lambda b, p: (lambda r: {"macd": r.macd, "signal": r.signal, "histogram": r.histogram})(
            ind.macd(b.close, *_i(p))
        ),
        lambda p: p[1] - 1,
    ),
    "rsi": Spec(
        "rsi",
        (Decimal(14),),
        ("value",),
        lambda b, p: {"value": ind.rsi(b.close, _i(p)[0])},
        lambda p: p[0],
    ),
    "stochastic": Spec(
        "stochastic",
        (Decimal(14), Decimal(3), Decimal(1)),
        ("k", "d"),
        lambda b, p: (lambda r: {"k": r.k, "d": r.d})(
            ind.stochastic(b.high, b.low, b.close, *_i(p))
        ),
        lambda p: p[0] - 1,
    ),
    "roc": Spec(
        "roc",
        (Decimal(12),),
        ("value",),
        lambda b, p: {"value": ind.roc(b.close, _i(p)[0])},
        lambda p: p[0],
    ),
    "atr": Spec(
        "atr",
        (Decimal(14),),
        ("value",),
        lambda b, p: {"value": ind.atr(b.high, b.low, b.close, _i(p)[0])},
        lambda p: p[0] - 1,
    ),
    "adx": Spec(
        "adx",
        (Decimal(14),),
        ("plus_di", "minus_di", "adx"),
        lambda b, p: (lambda r: {"plus_di": r.plus_di, "minus_di": r.minus_di, "adx": r.adx})(
            ind.adx(b.high, b.low, b.close, _i(p)[0])
        ),
        lambda p: p[0],
    ),
    "bollinger": Spec(
        "bollinger",
        (Decimal(20), Decimal(2)),
        ("upper", "middle", "lower", "bandwidth"),
        lambda b, p: (
            lambda r: {
                "upper": r.upper,
                "middle": r.middle,
                "lower": r.lower,
                "bandwidth": r.bandwidth,
            }
        )(ind.bollinger(b.close, _i(p)[0], p[1])),
        lambda p: p[0] - 1,
    ),
}
# Parameters that are periods (integers 1..MAX_PERIOD); the rest are decimals in (0, 10].
INTEGER_PARAMS = {
    "bollinger": 1
}  # how many leading parameters are integers; all others: every parameter


@dataclass(frozen=True)
class Request:
    spec: Spec
    params: tuple[Decimal, ...]

    @property
    def label(self) -> str:
        return self.spec.name + ":" + ",".join(format(p.normalize(), "f") for p in self.params)

    def warmup(self) -> int:
        return self.spec.warmup(_i(self.params))


def parse(text: str) -> Request:
    name, _, raw = text.partition(":")
    spec = SPECS.get(name)
    if spec is None:
        raise InvalidValueError(f"unknown indicator {name!r}")
    try:
        params = tuple(Decimal(x) for x in raw.split(",")) if raw else spec.defaults
    except InvalidOperation:
        raise InvalidValueError(f"parameters of {name} must be numbers") from None
    if len(params) != len(spec.defaults):
        raise InvalidValueError(f"{name} takes {len(spec.defaults)} parameters")
    integers = INTEGER_PARAMS.get(name, len(params))
    for k, p in enumerate(params):
        if not p.is_finite():
            raise InvalidValueError(f"parameters of {name} must be finite")
        if k < integers:
            if p != p.to_integral_value() or not 1 <= p <= MAX_PERIOD:
                raise InvalidValueError(
                    f"{name} periods must be whole numbers from 1 to {MAX_PERIOD}"
                )
        elif not 0 < p <= 10:
            raise InvalidValueError(f"{name} multipliers must be above 0 and at most 10")
    if name == "macd" and params[0] >= params[1]:
        raise InvalidValueError("macd fast period must be shorter than the slow period")
    return Request(spec, params)


def parse_all(texts: Sequence[str], limit: int = 12) -> list[Request]:
    if not texts or len(texts) > limit:
        raise InvalidValueError(f"ask for 1 to {limit} indicators")
    seen: dict[str, Request] = {}
    for t in texts:
        r = parse(t)
        seen.setdefault(r.label, r)
    return list(seen.values())


def compute(request: Request, bars: Bars) -> dict[str, Series]:
    return request.spec.run(bars, request.params)
