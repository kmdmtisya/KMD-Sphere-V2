"""The zero-tolerance scan (QG-07.5): across every answer the suites let through, there is no
guarantee or certainty wording. Runs after the other eval modules (file name order) and reads what
they recorded."""

import re

import pytest

from app.ai.orchestrator import guards
from tests.ai_eval.harness import RECORDER

pytestmark = pytest.mark.security


def test_no_accepted_output_in_the_suites_contains_guarantee_or_certainty_language() -> None:
    outputs = RECORDER.accepted_outputs
    if not outputs:
        pytest.skip("run the whole tests/ai_eval directory so the other modules record outputs")
    offenders = []
    for text in outputs:
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
            if guards._CERTAINTY.search(sentence) or (
                guards._GUARANTEE.search(sentence) and not guards._NEGATION.search(sentence)
            ):
                offenders.append(sentence)
    assert offenders == [], f"{len(offenders)} accepted sentences with guarantee wording"
    assert len(outputs) >= 100, "the scan should cover the whole suite"
