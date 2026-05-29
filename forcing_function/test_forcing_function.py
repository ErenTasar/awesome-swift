"""Proof that the forcing function holds.

The headline tests run an *adversarial* model that always tries to finalize a
claim as early as possible — skipping the source, skipping the reconciliation
edge. The mask makes those shortcuts un-emittable, so every claim it produces is
nonetheless well-formed. (It can still lie: a forced source may be "UNVERIFIED".
The format guarantees presence and shape, never truth.)
"""

import pytest

from forcing_function.constrained_decode import (
    ForcingDecoder, IllegalAction,
    START, TEXT, SRC, KEY, REL, CLOSE, EOF, RECONCILERS,
)
from forcing_function.models import AdversarialModel, CooperativeModel


# --- headline: the adversary cannot escape the constraints ------------------

def test_provenance_is_forced_even_against_an_adversary():
    plan = [{"text": "half-life is 5h"}]          # note: no source intended
    claims = ForcingDecoder().generate(AdversarialModel(plan))
    assert len(claims) == 1
    assert claims[0].src, "a claim with an empty source must be un-emittable"


def test_reconciliation_is_forced_even_against_an_adversary():
    # Two claims about the same key => the second must carry a reconciling edge,
    # even though the adversary tries to close it bare.
    plan = [
        {"text": "half-life is 5h", "key": "half-life", "id": "a1"},
        {"text": "half-life is 3h", "key": "half-life", "id": "a2"},
    ]
    claims = ForcingDecoder().generate(AdversarialModel(plan))
    a2 = claims[1]
    assert any(rt in RECONCILERS and tgt in {"a1"} for rt, tgt in a2.rels), \
        "a second claim on a seen key must be forced to reconcile"


def test_unkeyed_claims_need_no_reconciliation():
    # Without a shared key there is no conflict, so only provenance is forced.
    plan = [{"text": "x"}, {"text": "y"}]
    claims = ForcingDecoder().generate(AdversarialModel(plan))
    assert all(c.src for c in claims)
    assert all(c.rels == [] for c in claims)


# --- direct mask behaviour --------------------------------------------------

def test_close_is_masked_until_a_source_exists():
    d = ForcingDecoder()
    d.apply(START)
    d.apply(TEXT, "a claim")
    assert CLOSE not in d.legal_types()           # provenance not yet satisfied
    with pytest.raises(IllegalAction):
        d.apply(CLOSE, "c0")
    d.apply(SRC, "who-2020")
    assert CLOSE in d.legal_types()               # now finalizable


def test_close_is_masked_until_a_conflict_is_reconciled():
    d = ForcingDecoder()
    d.apply(START); d.apply(TEXT, "5h"); d.apply(SRC, "who-2020")
    d.apply(KEY, "half-life"); d.apply(CLOSE, "a1")
    # second claim, same key
    d.apply(START); d.apply(TEXT, "3h"); d.apply(SRC, "smith-1998")
    d.apply(KEY, "half-life")
    assert CLOSE not in d.legal_types()           # conflict unreconciled
    assert REL in d.legal_types()
    with pytest.raises(IllegalAction):
        d.apply(CLOSE, "a2")
    d.apply(REL, ("supersedes", "a1"))
    assert CLOSE in d.legal_types()


def test_empty_source_is_illegal():
    d = ForcingDecoder()
    d.apply(START); d.apply(TEXT, "a claim")
    with pytest.raises(IllegalAction):
        d.apply(SRC, "")


def test_edge_must_resolve_to_an_existing_claim():
    d = ForcingDecoder()
    d.apply(START); d.apply(TEXT, "5h"); d.apply(SRC, "x")
    d.apply(KEY, "k"); d.apply(CLOSE, "a1")
    d.apply(START); d.apply(TEXT, "3h"); d.apply(SRC, "y"); d.apply(KEY, "k")
    with pytest.raises(IllegalAction):
        d.apply(REL, ("supersedes", "does-not-exist"))


def test_duplicate_claim_id_is_illegal():
    d = ForcingDecoder()
    d.apply(START); d.apply(TEXT, "a"); d.apply(SRC, "x")
    d.apply(CLOSE, "a1")
    d.apply(START); d.apply(TEXT, "b"); d.apply(SRC, "y")
    with pytest.raises(IllegalAction):
        d.apply(CLOSE, "a1")


def test_cooperative_model_generates_a_valid_document():
    plan = [
        {"text": "half-life ~5h", "src": "who-2020", "key": "half-life", "id": "a1"},
        {"text": "older estimate 3h", "src": "smith-1998", "key": "half-life",
         "id": "a2", "rels": [("supersedes", "a1")]},
    ]
    claims = ForcingDecoder().generate(CooperativeModel(plan))
    assert [c.id for c in claims] == ["a1", "a2"]
    assert claims[1].rels == [("supersedes", "a1")]


# --- emit(): the ergonomic in-the-loop entry point --------------------------

def test_emit_refuses_a_claim_without_a_source():
    d = ForcingDecoder()
    with pytest.raises(IllegalAction):
        d.emit(cid="c1", text="a fact", key="k")           # no src
    assert d.state.output == []                            # atomic: nothing kept


def test_emit_refuses_an_unreconciled_conflict():
    d = ForcingDecoder()
    d.emit(cid="c1", text="5h", src="who", key="hl")
    with pytest.raises(IllegalAction):
        d.emit(cid="c2", text="3h", src="smith", key="hl")  # conflict, no edge
    assert [c.id for c in d.state.output] == ["c1"]          # atomic


def test_emit_succeeds_when_requirements_are_met():
    d = ForcingDecoder()
    d.emit(cid="c1", text="5h", src="who", key="hl")
    c2 = d.emit(cid="c2", text="3h", src="smith", key="hl",
                rels=[("supersedes", "c1")])
    assert c2.rels == [("supersedes", "c1")]


def test_whitespace_only_source_is_illegal():
    # found by a real model in the loop: " " is truthy but not a source.
    d = ForcingDecoder()
    with pytest.raises(IllegalAction):
        d.emit(cid="c1", text="a fact", src="   ")
    d.apply(START); d.apply(TEXT, "a fact")
    with pytest.raises(IllegalAction):
        d.apply(SRC, "  ")
