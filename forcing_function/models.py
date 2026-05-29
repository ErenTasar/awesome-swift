"""Toy 'models' that drive the decoder. A real LLM would replace these: its
logits propose actions, and the decoder's mask removes the illegal ones."""

from forcing_function.constrained_decode import (
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
