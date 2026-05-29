"""Tests for the grounding layer: resolvable source + verbatim quote, and the
honest limit (a real-but-irrelevant quote is only caught by a fallible judge)."""

import pytest

from forcing_function.constrained_decode import ForcingDecoder
from forcing_function.grounded import (
    SourcePool, emit_grounded,
    UnresolvableSource, FabricatedQuote, UnfaithfulCitation)


POOL = SourcePool({
    "iau-2006": "In 2006 the IAU defined a planet and reclassified Pluto as a "
                "dwarf planet.",
    "nist": "The boiling point of water is 100 C at standard atmospheric "
            "pressure.",
})


def test_invented_source_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(UnresolvableSource):
        emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="general astronomical knowledge",   # not in the pool
                      quote="reclassified Pluto as a dwarf planet")
    assert d.state.output == []                               # atomic


def test_fabricated_quote_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="Pluto was deleted from the sky")   # not in the text
    assert d.state.output == []


def test_quote_must_be_in_the_CITED_source_not_another():
    # Citing iau-2006 but quoting the NIST source is caught: the quote is not a
    # verbatim span of the cited source.
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="100 C at standard atmospheric pressure")


def test_resolvable_and_verbatim_passes():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="reclassified Pluto as a dwarf planet")
    assert c.src == "iau-2006"
    assert c.quote == "reclassified Pluto as a dwarf planet"


def test_judge_can_reject_a_real_but_unsupportive_quote():
    # The honest limit: this quote IS verbatim in the source, so tiers 1+2 pass.
    # Only a semantic judge can notice it does not support the claim.
    d = ForcingDecoder()

    def judge(claim_text, quote):
        # toy stand-in for an NLI/LLM gate
        return "dwarf planet" in quote and "dwarf planet" in claim_text

    with pytest.raises(UnfaithfulCitation):
        emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="In 2006 the IAU defined a planet",   # real, unrelated
                      judge=judge)


def test_judge_passes_a_supportive_quote():
    d = ForcingDecoder()

    def judge(claim_text, quote):
        return "dwarf planet" in quote and "dwarf planet" in claim_text

    c = emit_grounded(d, POOL, cid="c1",
                      text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="reclassified Pluto as a dwarf planet",
                      judge=judge)
    assert c.quote == "reclassified Pluto as a dwarf planet"


def test_reconciliation_still_applies_on_top_of_grounding():
    d = ForcingDecoder()
    emit_grounded(d, POOL, cid="c1", text="Water boils at 100 C.",
                  src="nist", quote="boiling point of water is 100 C",
                  key="boil")
    # a second, conflicting claim on the same key still needs a reconciling edge
    with pytest.raises(Exception):
        emit_grounded(d, POOL, cid="c2", text="Water boils at 90 C.",
                      src="nist", quote="boiling point of water is 100 C",
                      key="boil")
