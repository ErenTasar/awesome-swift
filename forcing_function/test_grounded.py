"""Tests for the citation ledger — the API-only core.

Two primitives plus reconciliation, all reached through GroundedDecoder.cite():
  1. mechanical provenance integrity (resolvable, verbatim, tamper-evident,
     trusted-origin, optional extractive) — finite and sound;
  2. reconciliation — conflicting claims (shared key) need an explicit edge;
  3. one semantic judge that sees the FULL source — the only place meaning lives.
"""

import pytest

from forcing_function.grounded import (
    SourcePool, GroundedDecoder, Claim, reverify,
    UnresolvableSource, FabricatedQuote, UntrustedSource, NeedsReconciliation,
    UnfaithfulCitation, TamperedSource)


POOL = SourcePool({
    "iau-2006": "The IAU met in 2006. It reclassified Pluto as a dwarf planet.",
    "fee": "The fee is waived. However, this applies only to first-time filers.",
    "pk": "The drug reduces fever.",
    "old": "Pluto is the ninth planet.",
})

PLUTO = "It reclassified Pluto as a dwarf planet."


# --- 1. mechanical provenance integrity (sound, finite) ---------------------

def test_invented_source_is_impossible():
    gd = GroundedDecoder(POOL)
    with pytest.raises(UnresolvableSource):
        gd.cite(cid="c1", text="Pluto is a dwarf planet.",
                src="general knowledge", quote=PLUTO)
    assert gd.claims == []


def test_fabricated_quote_is_impossible():
    gd = GroundedDecoder(POOL)
    with pytest.raises(FabricatedQuote):
        gd.cite(cid="c1", text="Pluto is a dwarf planet.",
                src="iau-2006", quote="Pluto was deleted from the sky")


def test_quote_must_be_in_the_cited_source():
    gd = GroundedDecoder(POOL)
    with pytest.raises(FabricatedQuote):
        gd.cite(cid="c1", text="x", src="iau-2006",
                quote="The drug reduces fever.")   # lives in another source


def test_blank_quote_is_refused():
    gd = GroundedDecoder(POOL)
    with pytest.raises(FabricatedQuote):
        gd.cite(cid="c1", text="x", src="iau-2006", quote="   ")


def test_well_grounded_claim_passes():
    gd = GroundedDecoder(POOL)
    c = gd.cite(cid="c1", text="Pluto is a dwarf planet.",
                src="iau-2006", quote=PLUTO)
    assert c.src == "iau-2006" and c.quote == PLUTO and c.src_hash
    assert gd.claims[-1] is c


# --- extractive mode (sound: an exact equality, not a heuristic) ------------

def test_extractive_requires_the_claim_to_be_the_quote():
    gd = GroundedDecoder(POOL, extractive=True)
    with pytest.raises(FabricatedQuote):
        gd.cite(cid="c1", text="Fever reduces the drug.",
                src="pk", quote="The drug reduces fever.")


def test_extractive_accepts_the_verbatim_claim():
    gd = GroundedDecoder(POOL, extractive=True)
    c = gd.cite(cid="c1", text="The drug reduces fever.",
                src="pk", quote="The drug reduces fever.")
    assert c.text == c.quote


# --- 2. reconciliation ------------------------------------------------------

def test_conflicting_key_needs_a_reconciling_edge():
    gd = GroundedDecoder(POOL)
    gd.cite(cid="c1", text="Pluto is the ninth planet.", src="old",
            quote="Pluto is the ninth planet.", key="pluto")
    with pytest.raises(NeedsReconciliation):
        gd.cite(cid="c2", text="Pluto is a dwarf planet.", src="iau-2006",
                quote=PLUTO, key="pluto")              # conflict, no edge


def test_reconciling_edge_lets_the_conflict_through():
    gd = GroundedDecoder(POOL)
    gd.cite(cid="c1", text="Pluto is the ninth planet.", src="old",
            quote="Pluto is the ninth planet.", key="pluto")
    c2 = gd.cite(cid="c2", text="Pluto is a dwarf planet.", src="iau-2006",
                 quote=PLUTO, key="pluto", rels=[("supersedes", "c1")])
    assert c2.rels == [("supersedes", "c1")]


def test_edge_must_resolve_to_an_existing_claim():
    gd = GroundedDecoder(POOL)
    with pytest.raises(NeedsReconciliation):
        gd.cite(cid="c1", text="Pluto is a dwarf planet.", src="iau-2006",
                quote=PLUTO, rels=[("supersedes", "nope")])


def test_conflict_edge_must_target_a_same_key_claim():
    # Pentest V1: reusing a key must be reconciled against a claim that *shares
    # that key*. An edge to an unrelated claim resolves structurally but leaves
    # the actual conflict unrecorded, so it must be refused.
    gd = GroundedDecoder(POOL)
    gd.cite(cid="c1", text="Pluto is the ninth planet.", src="old",
            quote="Pluto is the ninth planet.", key="pluto")
    gd.cite(cid="unrelated", text="The fee is waived.", src="fee",
            quote="The fee is waived.", key="fee")
    with pytest.raises(NeedsReconciliation):
        gd.cite(cid="c2", text="Pluto is a dwarf planet.", src="iau-2006",
                quote=PLUTO, key="pluto", rels=[("refines", "unrelated")])
    assert [c.id for c in gd.claims] == ["c1", "unrelated"]
    # The same edge, pointed at the conflicting same-key claim, is accepted.
    c2 = gd.cite(cid="c2", text="Pluto is a dwarf planet.", src="iau-2006",
                 quote=PLUTO, key="pluto", rels=[("supersedes", "c1")])
    assert c2.rels == [("supersedes", "c1")]


def test_duplicate_id_is_refused():
    gd = GroundedDecoder(POOL)
    gd.cite(cid="c1", text="The drug reduces fever.", src="pk",
            quote="The drug reduces fever.")
    with pytest.raises(NeedsReconciliation):
        gd.cite(cid="c1", text="Pluto is a dwarf planet.", src="iau-2006",
                quote=PLUTO)


# --- 3. the single judge, with full context, owns all meaning ---------------

def test_judge_with_full_context_catches_cherry_picking():
    # The quote is a true verbatim sentence, but the source's next sentence
    # qualifies it. No mechanical check sees that; a judge given the whole
    # source can. This is the case that used to need an endless heuristic.
    def judge(claim, quote, source):
        return not ("only" in source.lower() and "only" not in claim.lower())

    gd = GroundedDecoder(POOL, judge=judge)
    with pytest.raises(UnfaithfulCitation):
        gd.cite(cid="c1", text="The fee is waived.",
                src="fee", quote="The fee is waived.")


def test_judge_receives_the_whole_source():
    seen = {}

    def judge(claim, quote, source):
        seen["source"] = source
        return True

    GroundedDecoder(POOL, judge=judge).cite(
        cid="c1", text="Pluto is a dwarf planet.", src="iau-2006", quote=PLUTO)
    assert seen["source"] == POOL.text("iau-2006")     # full text, not just quote


def test_no_judge_means_only_integrity_is_checked():
    # Honest: without a judge a relation reversal passes (mechanics cannot see
    # meaning). The judge is the only line; stated, not hidden.
    gd = GroundedDecoder(POOL)
    c = gd.cite(cid="c1", text="Fever reduces the drug.",
                src="pk", quote="The drug reduces fever.")
    assert c.quote == "The drug reduces fever."


# --- trusted link: fails closed --------------------------------------------

def test_untrusted_origin_is_refused():
    pool = SourcePool({"x": "Vaccines cause harm."},
                      uris={"x": "http://evil.example/forged"},
                      trusted_domains={"eur-lex.europa.eu"})
    gd = GroundedDecoder(pool, require_trusted_link=True)
    with pytest.raises(UntrustedSource):
        gd.cite(cid="c1", text="Vaccines cause harm.",
                src="x", quote="Vaccines cause harm.")


def test_required_link_fails_closed_when_no_allowlist():
    pool = SourcePool({"x": "The sky is blue."},
                      uris={"x": "http://anything.example/x"})  # trusted_domains=None
    gd = GroundedDecoder(pool, require_trusted_link=True)
    with pytest.raises(UntrustedSource):
        gd.cite(cid="c1", text="The sky is blue.", src="x", quote="The sky is blue.")


def test_trusted_origin_passes_and_records_uri():
    pool = SourcePool({"reg": "The additive is banned in food."},
                      uris={"reg": "https://eur-lex.europa.eu/eli/reg/2023/1"},
                      trusted_domains={"eur-lex.europa.eu"})
    gd = GroundedDecoder(pool, require_trusted_link=True)
    c = gd.cite(cid="c1", text="The additive is banned in food.",
                src="reg", quote="The additive is banned in food.")
    assert c.uri == "https://eur-lex.europa.eu/eli/reg/2023/1"


# --- tamper-evidence: fails closed -----------------------------------------

def test_reverify_passes_against_untouched_pool():
    gd = GroundedDecoder(POOL)
    c = gd.cite(cid="c1", text="Pluto is a dwarf planet.", src="iau-2006", quote=PLUTO)
    assert reverify(POOL, c) is True


def test_reverify_detects_tampering():
    gd = GroundedDecoder(POOL)
    c = gd.cite(cid="c1", text="Pluto is a dwarf planet.", src="iau-2006", quote=PLUTO)
    poisoned = SourcePool(dict(POOL.sources,
                               **{"iau-2006": "The IAU declared Pluto a planet."}))
    with pytest.raises(TamperedSource):
        reverify(poisoned, c)


def test_reverify_fails_closed_without_a_hash():
    fake = Claim(id="c1", text="x", src="iau-2006", quote=PLUTO, src_hash=None)
    with pytest.raises(TamperedSource):
        reverify(POOL, fake)


def test_reverify_fails_closed_on_blank_quote():
    # Pentest V3: cite() refuses a blank quote, so reverify must too. A claim
    # arriving (e.g. across a boundary) with an empty quote is unverifiable, not
    # vacuously valid.
    from forcing_function.grounded import fingerprint
    blank = Claim(id="c1", text="An unsupported assertion.", src="iau-2006",
                  quote="", src_hash=fingerprint(POOL.text("iau-2006")))
    with pytest.raises(TamperedSource):
        reverify(POOL, blank)


def test_reverify_rechecks_trust_when_required():
    pool = SourcePool({"reg": "The additive is banned in food."},
                      uris={"reg": "https://eur-lex.europa.eu/eli/reg/2023/1"},
                      trusted_domains={"eur-lex.europa.eu"})
    gd = GroundedDecoder(pool, require_trusted_link=True)
    c = gd.cite(cid="c1", text="The additive is banned in food.",
                src="reg", quote="The additive is banned in food.")
    repointed = SourcePool(pool.sources, uris={"reg": "https://evil.example/x"},
                           trusted_domains={"eur-lex.europa.eu"})
    with pytest.raises(TamperedSource):
        reverify(repointed, c, require_trusted_link=True)


# --- the surface is the only path (no ungrounded emit/apply) ----------------

def test_surface_exposes_only_cite():
    gd = GroundedDecoder(POOL)
    assert hasattr(gd, "cite")
    assert not hasattr(gd, "emit") and not hasattr(gd, "apply")


# --- agent-pipeline: temporal trust handoff (reverify catches drift) --------

def test_reverify_flags_content_drift_and_link_repoint():
    TRUSTED = {"eur-lex.europa.eu"}
    s0 = {"a": "Limit is 5 mg/kg.", "b": "Permits last 12 months."}
    u0 = {"a": "https://eur-lex.europa.eu/a", "b": "https://eur-lex.europa.eu/b"}
    gd = GroundedDecoder(SourcePool(s0, uris=u0, trusted_domains=TRUSTED),
                         require_trusted_link=True)
    ca = gd.cite(cid="a", text="Limit is 5 mg/kg.", src="a", quote="Limit is 5 mg/kg.")
    cb = gd.cite(cid="b", text="Permits last 12 months.", src="b",
                 quote="Permits last 12 months.")
    # drift: a's content changes, b's link repoints off-allowlist
    drifted = SourcePool({"a": "Limit is 50 mg/kg.", "b": "Permits last 12 months."},
                         uris={"a": "https://eur-lex.europa.eu/a",
                               "b": "https://evil.example/b"},
                         trusted_domains=TRUSTED)
    with pytest.raises(TamperedSource):
        reverify(drifted, ca, require_trusted_link=True)      # content drift
    with pytest.raises(TamperedSource):
        reverify(drifted, cb, require_trusted_link=True)      # link repoint
