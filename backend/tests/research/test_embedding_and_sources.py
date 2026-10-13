"""Research embeddings and sources (P12-T05): a deterministic embedder, the DEMO notes, and the
EDGAR submissions adapter on a synthetic fixture (no network)."""

import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.research.embedding import DIMENSIONS, HashEmbedder, build_embedder, tokens
from app.modules.research.sources import DemoResearchSource, EdgarSubmissionsSource

FIXTURE = Path(__file__).parent / "fixtures" / "edgar_submissions_demo.json"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_the_hash_embedder_is_deterministic_normalised_and_word_based() -> None:
    e = HashEmbedder()
    one, again = e.embed(["Bond prices fall when rates rise"] * 2)
    assert one == again and len(one) == DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in one)), 1.0)
    near, far = e.embed(["interest rates and bond prices", "crypto custody risk"])
    assert cosine(one, near) > cosine(one, far)
    assert e.embed([""]) == [[0.0] * DIMENSIONS], "no words, no direction"
    assert tokens("The bond, AND the rate!") == ["bond", "rate"]


def test_only_known_embedders_are_built() -> None:
    assert isinstance(build_embedder("hash"), HashEmbedder)
    with pytest.raises(ValueError, match="unknown research embedder"):
        build_embedder("someone-elses-api")


def test_the_demo_notes_are_all_labelled_and_fictional() -> None:
    source = DemoResearchSource()
    retrieved, entries = source.load()
    assert source.is_demo and source.licence_status == "demo"
    assert len(entries) == 16 and len({e.source_id for e in entries}) == 16
    for e in entries:
        assert e.title.startswith("DEMO note:") and e.summary.startswith("DEMO research.")
        assert e.published_at <= retrieved
        assert e.symbol is None or e.symbol.startswith("DEMO-")
    for word in ("guarantee", "will rise", "certain", "should buy"):
        assert all(word not in e.summary.lower() for e in entries), word


def test_edgar_filings_of_the_chosen_forms_with_their_archive_links() -> None:
    at = datetime(2026, 10, 13, tzinfo=UTC)
    source = EdgarSubmissionsSource(FIXTURE, at, is_demo=True, symbol="DMOH")
    retrieved, entries = source.load()
    assert retrieved == at and source.licence_status == "demo", "a fixture is DEMO data"
    assert EdgarSubmissionsSource(FIXTURE, at).licence_status == "public_domain"
    assert [e.source_id for e in entries] == [
        "0000000042-26-000010",
        "0000000042-26-000008",
        "0000000042-26-000007",
    ], "the insider form 4 is left out"
    first = entries[0]
    assert first.title == "Demo Holdings Inc: 10-Q filed 2026-08-05"
    assert first.summary == "10-Q filing by Demo Holdings Inc: Quarterly report."
    assert first.source_url == (
        "https://www.sec.gov/Archives/edgar/data/42/000000004226000010/dmoh-20260630.htm"
    )
    assert first.published_at == datetime(2026, 8, 5, tzinfo=UTC) and first.kind == "filing"
