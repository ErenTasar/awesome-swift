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


class AdversarialModel:
    """Wants every claim to have NO source and NO reconciliation, closed ASAP.
    It still emits the *content* it intends to assert (its body and its key),
    because that is what it means to make the claim — then it tries to cut every
    corner the mask will let it."""

    def __init__(self, plan):
        self.plan = list(plan)   # each: {"text":..., "key":?, "id":?}
        self.i = 0

    def propose(self, state, legal):
        if state.cur is None:
            return (START, None) if self.i < len(self.plan) else (EOF, None)
        cur = state.cur
        spec = self.plan[self.i]
        prefs = []
        if cur.text is None:
            prefs.append((TEXT, spec["text"]))
        if spec.get("key") and cur.key is None:
            prefs.append((KEY, spec["key"]))
        # The lazy desire: close before supplying provenance / reconciliation.
        cid = spec.get("id") or f"c{len(state.claims)}"
        prefs.append((CLOSE, cid))
        # Forced fillers, only reachable when CLOSE is masked. Values are junk:
        # presence under coercion, not honest content.
        if cur.src is None:
            prefs.append((SRC, "UNVERIFIED"))
        need_edge = (cur.key in state.seen_keys and not any(
            rt in RECONCILERS and tgt in state.ids for rt, tgt in cur.rels))
        if need_edge and state.ids:
            prefs.append((REL, ("supersedes", sorted(state.ids)[0])))
        for atype, val in prefs:
            if atype in legal:
                if atype == CLOSE:
                    self.i += 1
                return (atype, val)
        raise AssertionError(f"adversary stuck; legal={sorted(legal)}")


class CooperativeModel:
    """Supplies real sources and edges from its plan."""

    def __init__(self, plan):
        self.plan = list(plan)
        self.i = 0

    def propose(self, state, legal):
        if state.cur is None:
            return (START, None) if self.i < len(self.plan) else (EOF, None)
        cur = state.cur
        spec = self.plan[self.i]
        if cur.text is None:
            return (TEXT, spec["text"])
        if cur.src is None:
            return (SRC, spec["src"])
        if spec.get("key") and cur.key is None:
            return (KEY, spec["key"])
        for r in spec.get("rels", []):
            if r not in cur.rels:
                return (REL, r)
        self.i += 1
        return (CLOSE, spec["id"])


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
