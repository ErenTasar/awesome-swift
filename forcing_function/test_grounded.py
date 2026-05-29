"""Tests for the grounding layer's two primitives:
  1. mechanical provenance integrity (resolvable, verbatim, tamper-evident,
     trusted-origin, optional extractive) — finite and sound;
  2. one semantic judge that sees the FULL source — the only place meaning is
     decided. No word/sentence heuristics remain.
"""

import pytest

from forcing_function.constrained_decode import ForcingDecoder
from forcing_function.grounded import (
    SourcePool, GroundedDecoder, emit_grounded, reverify,
    UnresolvableSource, FabricatedQuote, UntrustedSource, UnfaithfulCitation,
    TamperedSource)


POOL = SourcePool({
    "iau-2006": "The IAU met in 2006. It reclassified Pluto as a dwarf planet.",
    "fee": "The fee is waived. However, this applies only to first-time filers.",
    "pk": "The drug reduces fever.",
})

PLUTO = "It reclassified Pluto as a dwarf planet."


# --- 1. mechanical provenance integrity (sound, finite) ---------------------

def test_invented_source_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(UnresolvableSource):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="general knowledge", quote=PLUTO)
    assert d.state.output == []


def test_fabricated_quote_is_impossible():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote="Pluto was deleted from the sky")


def test_quote_must_be_in_the_cited_source():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="x", src="iau-2006",
                      quote="The drug reduces fever.")   # lives in another source


def test_blank_quote_is_refused():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="x", src="iau-2006", quote="   ")


def test_well_grounded_claim_passes():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    assert c.src == "iau-2006" and c.quote == PLUTO and c.src_hash


# --- extractive mode (sound: an exact equality, not a heuristic) ------------

def test_extractive_requires_the_claim_to_be_the_quote():
    d = ForcingDecoder()
    with pytest.raises(FabricatedQuote):
        emit_grounded(d, POOL, cid="c1", text="Fever reduces the drug.",
                      src="pk", quote="The drug reduces fever.", extractive=True)


def test_extractive_accepts_the_verbatim_claim():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="The drug reduces fever.",
                      src="pk", quote="The drug reduces fever.", extractive=True)
    assert c.text == c.quote


# --- 2. the single judge, with full context, owns all meaning ---------------

def test_judge_with_full_context_catches_cherry_picking():
    # The quote is a true verbatim sentence, but the source's NEXT sentence
    # qualifies it. No mechanical tier can see that; a judge given the whole
    # source can. This is the case that used to need an endless heuristic.
    d = ForcingDecoder()

    def judge(claim, quote, source):
        # a real judge is an NLI/LLM; here a stand-in: the claim is unfaithful if
        # the source qualifies the quote with a restricting clause it omits.
        return "only" not in source.lower() or "only" in claim.lower()

    with pytest.raises(UnfaithfulCitation):
        emit_grounded(d, POOL, cid="c1", text="The fee is waived.",
                      src="fee", quote="The fee is waived.", judge=judge)


def test_judge_receives_the_whole_source():
    seen = {}

    def judge(claim, quote, source):
        seen["source"] = source
        return True

    d = ForcingDecoder()
    emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                  src="iau-2006", quote=PLUTO, judge=judge)
    assert seen["source"] == POOL.text("iau-2006")     # full text, not just quote


def test_no_judge_means_only_integrity_is_checked():
    # Honest: without a judge, a relation reversal passes (mechanics cannot see
    # meaning). The judge is the only line; this is stated, not hidden.
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Fever reduces the drug.",
                      src="pk", quote="The drug reduces fever.")
    assert c.quote == "The drug reduces fever."


# --- trusted link: fails closed --------------------------------------------

def test_untrusted_origin_is_refused():
    pool = SourcePool({"x": "Vaccines cause harm."},
                      uris={"x": "http://evil.example/forged"},
                      trusted_domains={"eur-lex.europa.eu"})
    d = ForcingDecoder()
    with pytest.raises(UntrustedSource):
        emit_grounded(d, pool, cid="c1", text="Vaccines cause harm.",
                      src="x", quote="Vaccines cause harm.",
                      require_trusted_link=True)


def test_required_link_fails_closed_when_no_allowlist():
    # V4: require_trusted_link with no trusted_domains must REFUSE, not accept.
    pool = SourcePool({"x": "The sky is blue."},
                      uris={"x": "http://anything.example/x"})  # trusted_domains=None
    d = ForcingDecoder()
    with pytest.raises(UntrustedSource):
        emit_grounded(d, pool, cid="c1", text="The sky is blue.",
                      src="x", quote="The sky is blue.", require_trusted_link=True)


def test_trusted_origin_passes_and_records_uri():
    pool = SourcePool({"reg": "The additive is banned in food."},
                      uris={"reg": "https://eur-lex.europa.eu/eli/reg/2023/1"},
                      trusted_domains={"eur-lex.europa.eu"})
    d = ForcingDecoder()
    c = emit_grounded(d, pool, cid="c1", text="The additive is banned in food.",
                      src="reg", quote="The additive is banned in food.",
                      require_trusted_link=True)
    assert c.uri == "https://eur-lex.europa.eu/eli/reg/2023/1"


# --- tamper-evidence: fails closed -----------------------------------------

def test_reverify_passes_against_untouched_pool():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    assert reverify(POOL, c) is True


def test_reverify_detects_tampering():
    d = ForcingDecoder()
    c = emit_grounded(d, POOL, cid="c1", text="Pluto is a dwarf planet.",
                      src="iau-2006", quote=PLUTO)
    poisoned = SourcePool(dict(POOL.sources,
                               **{"iau-2006": "The IAU declared Pluto a planet."}))
    with pytest.raises(TamperedSource):
        reverify(poisoned, c)


def test_reverify_fails_closed_without_a_hash():
    # V6: a claim with no recorded hash is unverifiable, not silently valid.
    from forcing_function.constrained_decode import Claim
    fake = Claim(id="c1", text="x", src="iau-2006", quote=PLUTO, src_hash=None)
    with pytest.raises(TamperedSource):
        reverify(POOL, fake)


def test_reverify_rechecks_trust_when_required():
    # V5: a repointed link is caught on re-verification.
    pool = SourcePool({"reg": "The additive is banned in food."},
                      uris={"reg": "https://eur-lex.europa.eu/eli/reg/2023/1"},
                      trusted_domains={"eur-lex.europa.eu"})
    d = ForcingDecoder()
    c = emit_grounded(d, pool, cid="c1", text="The additive is banned in food.",
                      src="reg", quote="The additive is banned in food.",
                      require_trusted_link=True)
    repointed = SourcePool(pool.sources,
                           uris={"reg": "https://evil.example/x"},
                           trusted_domains={"eur-lex.europa.eu"})
    with pytest.raises(TamperedSource):
        reverify(repointed, c, require_trusted_link=True)


# --- the non-bypassable surface (V7) ----------------------------------------

def test_grounded_decoder_has_no_ungrounded_path():
    # V7: GroundedDecoder exposes only cite(); there is no bare emit()/apply().
    gd = GroundedDecoder(POOL)
    assert not hasattr(gd, "emit") and not hasattr(gd, "apply")
    c = gd.cite(cid="c1", text="Pluto is a dwarf planet.", src="iau-2006",
                quote=PLUTO)
    assert c.src == "iau-2006" and gd.claims[-1] is c
    with pytest.raises(UnresolvableSource):
        gd.cite(cid="c2", text="x", src="not-in-pool", quote=PLUTO)


def test_reconciliation_still_applies_through_the_surface():
    gd = GroundedDecoder(POOL)
    gd.cite(cid="c1", text="It reclassified Pluto as a dwarf planet.",
            src="iau-2006", quote=PLUTO, key="pluto")
    with pytest.raises(Exception):     # conflicting key, no reconciling edge
        gd.cite(cid="c2", text="The drug reduces fever.", src="pk",
                quote="The drug reduces fever.", key="pluto")
