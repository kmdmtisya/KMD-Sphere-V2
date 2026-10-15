"""The report document (P14-T15): a title, the facts every file must carry (when it was made, the
currency, the as-of time, the disclosures) and tables of strings. A report holds no calculation: its
figures are the decimal strings the platform's own services returned, so a file always agrees with
the screen for the same request (QG-30.1). Money columns are marked numeric so a spreadsheet gets
numbers; nothing is rounded or converted here."""

from dataclasses import dataclass, field
from datetime import datetime

KINDS = ("portfolio", "performance", "net-worth", "income", "goals")
FORMATS = ("csv", "xlsx", "pdf")

DISCLOSURES = (
    "WealthSphere reports describe your own recorded data. They are not investment, tax or legal "
    "advice.",
    "Past performance does not predict future results. Projections are illustrations under stated "
    "assumptions, never guaranteed returns.",
    "Values depend on the prices, valuations and exchange rates available at the as-of time; a "
    "figure marked incomplete leaves out what could not be priced or converted.",
)


@dataclass(frozen=True)
class Table:
    title: str
    columns: tuple[str, ...]
    rows: list[tuple[str, ...]]
    numeric: frozenset[int] = frozenset()  # column indexes holding decimal strings


@dataclass(frozen=True)
class Report:
    kind: str
    title: str
    generated_at: datetime
    currency: str
    as_of: datetime | None
    tables: list[Table]
    notes: list[str] = field(default_factory=list)  # report-specific caveats, before DISCLOSURES

    def facts(self) -> list[tuple[str, str]]:
        """The header block every file starts with."""
        rows = [
            ("Report", self.title),
            ("Generated", self.generated_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Currency", self.currency),
        ]
        if self.as_of is not None:
            rows.append(("Data as of", self.as_of.strftime("%Y-%m-%d %H:%M UTC")))
        return rows

    def disclosures(self) -> list[str]:
        return [*self.notes, *DISCLOSURES]
