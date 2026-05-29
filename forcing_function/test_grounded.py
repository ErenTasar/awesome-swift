"""Tests for the grounding layer.

Beyond resolvable-source + verbatim-whole-sentence (tiers 1/2/2b), these cover
the two 'creative hacks' that convert previously judge-only gaps into mechanical
checks: grounded-words (2c) and negation-parity (2d), plus tamper-evidence for
pool poisoning. The honest residue — correct relation among shared words — still
needs the fallible judge (tier 3)."""

import pytest

from forcing_function.constrained_decode import ForcingDecoder
from forcing_function.grounded import (
    SourcePool, emit_grounded, reverify,
    UnresolvableSource, FabricatedQuote, UngroundedClaim, UnfaithfulCitation,
    TamperedSource)


POOL = SourcePool({
    "iau-2006": "The IAU met in 2006. It reclassified Pluto as a dwarf planet.",
    "nist": "Water boils at 100 C at standard pressure. "
            "Pressure changes the boiling point.",
    "court": "The jury deliberated for a week. "
             "The defendant was found not guilty on all counts.",
    "pk": "The drug reduces fever.",
    "myth": "Some people think water boils at 90 C.",
})

PLUTO = "It reclassified Pluto as a dwarf planet."   # a whole sentence of iau-2006


# --- tiers 1 / 2 / 2b (mechanism, airtight) ---------------------------------

def test_invented_source_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(UnresolvableSource):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="general astronomical knowledge", quote=PLUTO)
    assert d.state.output == []


def test_fabricated_quote_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote="Pluto was deleted from the sky")


def test_quote_must_be_in_the_cited_source():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006",
                      quote="Water boils at 100 C at standard pressure.")


def test_negation_dropping_subspan_is_refused():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="The defendant was convicted.",
                      src="court", quote="guilty on all counts.")


# --- tier 2c: grounded words (the hack against 'real but irrelevant quote') --

def test_irrelevant_whole_sentence_is_now_refused_mechanically():
    # Previously this needed a judge; 2c catches it: the claim's words
    # (pluto/dwarf/planet) are absent from the quote.
    d = ForcingDecoder()
    with pytest.raises(UngroundedClaim):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote="The IAU met in 2006.")


def test_claim_cannot_introduce_new_facts():
    # red-team 4a: real quote, claim asserts an unsupported conclusion.
    d = ForcingDecoder()
    with pytest.raises(UngroundedClaim):
        emit_grounded(
            d, POOL, cid="c1",
            text="The patient has cancer and needs chemotherapy.",
            src="iau-2006", quote=PLUTO)


# --- tier 2d: negation parity (polarity flip using the source's own words) ---

def test_polarity_flip_with_source_words_is_refused():
    # The claim uses only words present in the quote but drops the negation:
    # "not guilty" -> "guilty". 2c passes (words match); 2d catches the flip.
    d = ForcingDecoder()
    with pytest.raises(UngroundedClaim):
        emit_grounded(
            d, POOL, cid="c1",
            text="The defendant was found guilty on all counts.",
            src="court",
            quote="The defendant was found not guilty on all counts.")


# --- tier 3: the honest residue still needs a judge -------------------------

def test_relation_reversal_passes_mechanics_and_needs_a_judge():
    # Claim uses only the quote's words, with matching polarity, but reverses the
    # relation ("fever reduces the drug"). Mechanics cannot catch it; the judge
    # is the only line. With no judge it is ACCEPTED (stated honestly).
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Fever reduces the drug.",
                      src="pk", quote="The drug reduces fever.")
    assert c.quote == "The drug reduces fever."     # mechanics let it through

    # A semantic judge is required to reject it.
    d2 = ForcingDecoder()

    def judge(claim_text, quote):
        return "drug reduces fever" in claim_text.lower()

    with pytest.raises(UnfaithfulCitation):
        emit_grounded(d2, POOL, cid="c1", text="Fever reduces the drug.",
                      src="pk", quote="The drug reduces fever.", judge=judge)


# --- happy paths ------------------------------------------------------------

def test_well_grounded_claim_passes():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    assert c.src == "iau-2006" and c.quote == PLUTO and c.src_hash


def test_reconciliation_still_applies_on_top_of_grounding():
    d = ForcingDecoder()
    emit_grounded(d, POOL, cid="c1", text="Water boils at 100 C.",
                  src="nist", quote="Water boils at 100 C at standard pressure.",
                  key="boil")
    with pytest.raises(Exception):    # conflicting claim, no reconciling edge
        emit_grounded(d, POOL, cid="c2", text="Water boils at 90 C.",
                      src="myth", quote="Some people think water boils at 90 C.",
                      key="boil")


# --- problem 2: pool poisoning -> tamper-evidence ---------------------------

def test_reverify_passes_against_an_untouched_pool():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    assert reverify(POOL, c) is True


def test_reverify_detects_a_tampered_source():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    poisoned = SourcePool(dict(POOL.sources,
                               **{"iau-2006": "The IAU met in 2006. "
                                              "It declared Pluto the tenth planet."}))
    with pytest.raises(TamperedSource):
        reverify(poisoned, c)


# --- extractive mode: makes the 'wrong relation' residue impossible ---------

def test_extractive_mode_blocks_relation_reversal():
    # The residue case (Fever reduces the drug) is refused without any judge,
    # because the claim must BE the quote verbatim.
    d = ForcingDecoder()
    with pytest.raises(UngroundedClaim):
        emit_grounded(d, POOL, cid="c1", text="Fever reduces the drug.",
                      src="pk", quote="The drug reduces fever.", extractive=True)


def test_extractive_mode_accepts_the_verbatim_claim():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="The drug reduces fever.",
                      src="pk", quote="The drug reduces fever.", extractive=True)
    assert c.text == c.quote


# --- trusted reference link: names the external trust root ------------------

def test_untrusted_link_is_refused():
    from forcing_function.grounded import UntrustedSource
    pool = SourcePool(
        {"x": "Vaccines cause harm."},
        uris={"x": "http://evil.example/forged"},
        trusted_domains={"eur-lex.europa.eu", "pubmed.ncbi.nlm.nih.gov"})
    d = ForcingDecoder()
    with pytest.raises(UntrustedSource):
        emit_grounded(d, pool, cid="c1", text="Vaccines cause harm.",
                      src="x", quote="Vaccines cause harm.",
                      require_trusted_link=True)


def test_trusted_link_passes_and_is_recorded():
    pool = SourcePool(
        {"reg": "The additive is banned in food."},
        uris={"reg": "https://eur-lex.europa.eu/eli/reg/2023/1"},
        trusted_domains={"eur-lex.europa.eu"})
    d = ForcingDecoder()
    c = emit_grounded(d, pool, cid="c1", text="The additive is banned in food.",
                      src="reg", quote="The additive is banned in food.",
                      require_trusted_link=True)
    assert c.uri == "https://eur-lex.europa.eu/eli/reg/2023/1"


def test_missing_link_is_refused_when_required():
    from forcing_function.grounded import UntrustedSource
    d = ForcingDecoder()
    with pytest.raises(UntrustedSource):   # POOL has no uris
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO, require_trusted_link=True)
