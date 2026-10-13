"""Research sources (P12-T05.2). A source turns its own format into `ResearchEntry` values; it
never fetches anything on its own (no network here).

- `DemoResearchSource`: synthetic, DEMO-labelled notes about the DEMO universe (demo_research.json).
- `EdgarSubmissionsSource`: filings listed in an SEC EDGAR "submissions" document (the documented
  `https://data.sec.gov/submissions/CIK##########.json` shape). Built and tested against a
  synthetic fixture only (approved for P12: no live call). EDGAR data is public; a live adapter
  would also need SEC's fair-access rules (a declared User-Agent, at most 10 requests a second).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Protocol

DEMO_FILE = Path(__file__).with_name("demo_research.json")
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


@dataclass(frozen=True)
class ResearchEntry:
    source_id: str
    title: str
    summary: str
    kind: str
    published_at: datetime
    source_url: str | None = None
    symbol: str | None = None  # the instrument it is about, by its universe symbol


class ResearchSource(Protocol):
    name: str
    is_demo: bool
    licence_status: str

    def load(self) -> tuple[datetime, Sequence[ResearchEntry]]:
        """The entries and when they were obtained."""
        ...


class DemoResearchSource:
    name = "demo"
    is_demo = True
    licence_status = "demo"

    def __init__(self, path: Path = DEMO_FILE) -> None:
        self._path = path

    def load(self) -> tuple[datetime, Sequence[ResearchEntry]]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(raw["retrieved_at"]), [
            ResearchEntry(
                source_id=i["id"],
                title=i["title"],
                summary=i["summary"],
                kind=i["kind"],
                published_at=datetime.fromisoformat(i["published_at"]),
                symbol=i.get("symbol"),
            )
            for i in raw["items"]
        ]


class EdgarSubmissionsSource:
    """Filings from one company's EDGAR submissions document."""

    name = "sec_edgar"

    def __init__(
        self,
        document: Path,
        retrieved_at: datetime,
        *,
        forms: frozenset[str] = frozenset({"10-K", "10-Q", "8-K", "20-F", "6-K"}),
        is_demo: bool = False,
        symbol: str | None = None,
    ) -> None:
        self._document = document
        self._retrieved_at = retrieved_at
        self._forms = forms
        self.is_demo = is_demo
        # EDGAR filings are public records; a synthetic fixture is DEMO data like any other.
        self.licence_status = "demo" if is_demo else "public_domain"
        self._symbol = symbol

    def load(self) -> tuple[datetime, Sequence[ResearchEntry]]:
        doc = json.loads(self._document.read_text(encoding="utf-8"))
        cik = str(int(doc["cik"]))
        company = doc["name"]
        recent = doc["filings"]["recent"]
        entries = []
        for accession, filed, form, primary, description in zip(
            recent["accessionNumber"],
            recent["filingDate"],
            recent["form"],
            recent["primaryDocument"],
            recent["primaryDocDescription"],
            strict=True,
        ):
            if form not in self._forms:
                continue
            folder = accession.replace("-", "")
            entries.append(
                ResearchEntry(
                    source_id=accession,
                    title=f"{company}: {form} filed {filed}",
                    summary=f"{form} filing by {company}"
                    + (f": {description}." if description else "."),
                    kind="filing",
                    published_at=datetime.combine(date.fromisoformat(filed), time.min, UTC),
                    source_url=f"{EDGAR_ARCHIVES}/{cik}/{folder}/{primary}",
                    symbol=self._symbol,
                )
            )
        return self._retrieved_at, entries
