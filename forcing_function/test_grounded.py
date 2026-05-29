"""Tests for the grounding layer: resolvable source + verbatim whole-sentence
quote, the red-team's negation-drop regression, and the honest limit (a
real-but-irrelevant whole sentence is only caught by a fallible judge)."""

import pytest

from forcing_function.constrained_decode import ForcingDecoder
from forcing_function.grounded import (
    SourcePool, emit_grounded,
    UnresolvableSource, FabricatedQuote, UnfaithfulCitation)


POOL = SourcePool({
    "iau-2006": "The IAU met in 2006. It reclassified Pluto as a dwarf planet.",
    "nist": "Water boils at 100 C at standard pressure. "
            "Pressure changes the boiling point.",
    "court": "The jury deliberated for a week. "
             "The defendant was found not guilty on all counts.",
})

PLUTO = "It reclassified Pluto as a dwarf planet."   # a whole sentence of iau-2006


def test_invented_source_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(UnresolvableSource):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="general astronomical knowledge",   # not in the pool
                      quote=PLUTO)
    assert d.state.output == []                               # atomic


def test_fabricated_quote_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="Pluto was deleted from the sky")   # in no source
    assert d.state.output == []


def test_quote_must_be_in_the_CITED_source_not_another():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="Water boils at 100 C at standard pressure.")


def test_negation_dropping_subspan_is_refused():
    # The red-team trick: "...found not guilty on all counts." has the verbatim
    # substring "guilty on all counts." which reverses the meaning. The
    # whole-sentence rule rejects it because it does not start at a sentence.
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="The defendant was convicted.",
                      src="court", quote="guilty on all counts.")


def test_single_word_or_punctuation_quote_is_refused():
    d = ForcingDecoder()
    for junk in ("The", "."):
        with pytest.raises(FabricatedQuote):
            emit_grounded(d, POOL, cid="c1", text="anything",
                          src="iau-2006", quote=junk)


def test_resolvable_and_whole_sentence_passes():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    assert c.src == "iau-2006"
    assert c.quote == PLUTO


def test_fragment_allowed_only_when_whole_sentence_disabled():
    # Opting out re-enables fragments (documented as less safe).
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote="reclassified Pluto as a dwarf planet",
                      whole_sentence=False)
    assert c.quote == "reclassified Pluto as a dwarf planet"
    # ...and the negation-drop trick comes back when you disable the rule:
    d2 = ForcingDecoder()
    c2 = emit_grounded(d2, POOL, cid="c1", text="The defendant was convicted.",
                       src="court", quote="guilty on all counts.",
                       whole_sentence=False)
    assert c2.quote == "guilty on all counts."   # honest: opt-out is weaker


def test_judge_can_reject_a_real_but_unsupportive_whole_sentence():
    # "The IAU met in 2006." is a whole sentence (passes tiers 1+2+2b) but does
    # not support the claim. Only a semantic judge notices.
    d = ForcingDecoder()

    def judge(claim_text, quote):
        return "dwarf planet" in quote and "dwarf planet" in claim_text

    with pytest.raises(UnfaithfulCitation):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote="The IAU met in 2006.", judge=judge)


def test_judge_passes_a_supportive_quote():
    d = ForcingDecoder()

    def judge(claim_text, quote):
        return "dwarf planet" in quote and "dwarf planet" in claim_text

    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO, judge=judge)
    assert c.quote == PLUTO


def test_reconciliation_still_applies_on_top_of_grounding():
    d = ForcingDecoder()
    emit_grounded(d, POOL, cid="c1", text="Water boils at 100 C.",
                  src="nist", quote="Water boils at 100 C at standard pressure.",
                  key="boil")
    with pytest.raises(Exception):    # conflicting claim, no reconciling edge
        emit_grounded(d, POOL, cid="c2", text="Water boils at 90 C.",
                      src="nist", quote="Water boils at 100 C at standard pressure.",
                      key="boil")
