"""A stateful, model-agnostic forcing-function decoder.

The point: an *invalid* output is un-emittable **by construction**. The decoder
exposes, at every step, only the set of legal next action-types; a model may
choose only among those. That is the software analogue of masking the logits of
illegal tokens. It does not validate after the fact — there is no "after", because
the illegal continuation was never offered.

Two constraints are enforced:

  1. PROVENANCE      a claim cannot be CLOSEd until it carries a non-empty source.
  2. RECONCILIATION  a claim whose `key` was already asserted by an earlier claim
                     cannot be CLOSEd until it emits a reconciling edge
                     (contradicts / supersedes / refines) to an existing claim.

Constraint 1 is context-free (a plain grammar can express it; see grammar.gbnf).
Constraint 2 is context-sensitive — legality of CLOSE depends on which keys were
emitted earlier in the document — so it cannot live in a context-free grammar and
requires the runtime state tracked here.

The decoder guarantees *presence and shape*, never truth: a forced source may be
invented, a forced edge may point at the wrong claim. Well-formedness, not virtue.
"""

from dataclasses import dataclass, field

RECONCILERS = {"contradicts", "supersedes", "refines"}

# Action types the decoder understands. These are the "tokens".
START = "START"   # open a new claim
TEXT  = "TEXT"    # emit the claim body            value: str
SRC   = "SRC"     # emit provenance                value: str (must be non-empty)
KEY   = "KEY"     # emit the claim-key             value: str
REL   = "REL"     # emit a reconciling edge        value: (reltype, target_id)
CLOSE = "CLOSE"   # finalize the current claim     value: claim_id
EOF   = "EOF"     # end the document


@dataclass
class _Building:
    """The claim currently under construction."""
    text: str = None
    src: str = None
    key: str = None
    rels: list = field(default_factory=list)   # list of (reltype, target_id)


@dataclass
class Claim:
    """A finalized claim."""
    id: str
    text: str
    src: str
    key: str = None
    rels: list = field(default_factory=list)
    quote: str = None          # set by the grounded layer: a verbatim span of src
    src_hash: str = None       # set by the grounded layer: fingerprint of src text
    uri: str = None            # set by the grounded layer: resolvable reference link


class State:
    def __init__(self):
        self.claims = []          # finalized, in order
        self.seen_keys = set()    # keys asserted by finalized claims
        self.ids = set()
        self.cur = None           # _Building or None
        self.done = False

    @property
    def output(self):
        return self.claims


class IllegalAction(Exception):
    """Raised if a caller bypasses legal_types() and applies a masked action."""


class NeedsProvenance(IllegalAction):
    """The model tried to finalize a claim with no non-empty source."""


class NeedsReconciliation(IllegalAction):
    """The model tried to finalize a claim that conflicts with an earlier one
    (same key) without an explicit reconciling edge."""


class ForcingDecoder:
    """Drives constrained generation. The model only ever sees legal types."""

    def __init__(self):
        self.state = State()

    # --- the mask -----------------------------------------------------------
    def legal_types(self):
        """The set of action-types allowed right now. This IS the mask."""
        st = self.state
        if st.done:
            return set()
        if st.cur is None:
            # between claims: open another, or finish the document
            return {START, EOF}
        cur = st.cur
        allowed = set()
        if cur.text is None:
            allowed.add(TEXT)            # body comes first
            return allowed
        # body emitted; optional fields may be added in any order
        allowed.add(SRC)
        allowed.add(KEY)
        if self._resolvable_targets():
            allowed.add(REL)
        if self._may_close():
            allowed.add(CLOSE)
        return allowed

    def _resolvable_targets(self):
        """Prior claim ids a REL could legally point at."""
        return set(self.state.ids)

    def _may_close(self):
        """The two forcing conditions, combined."""
        cur = self.state.cur
        if not cur.src:                                   # (1) provenance
            return False
        if cur.key in self.state.seen_keys:               # (2) reconciliation
            has_edge = any(rt in RECONCILERS and tgt in self.state.ids
                           for rt, tgt in cur.rels)
            if not has_edge:
                return False
        return True

    # --- apply --------------------------------------------------------------
    def apply(self, atype, value=None):
        """Apply one action, refusing anything the mask did not permit."""
        if atype not in self.legal_types():
            raise IllegalAction(
                f"{atype} is masked here; legal: {sorted(self.legal_types())}")
        st = self.state
        if atype == EOF:
            st.done = True
        elif atype == START:
            st.cur = _Building()
        elif atype == TEXT:
            if not (value and value.strip()):
                raise IllegalAction("TEXT must be non-blank")
            st.cur.text = value
        elif atype == SRC:
            if not (value and value.strip()):            # blank source is illegal
                raise IllegalAction("SRC must be non-blank")
            st.cur.src = value
        elif atype == KEY:
            st.cur.key = value
        elif atype == REL:
            reltype, target = value
            if reltype not in RECONCILERS or target not in st.ids:
                raise IllegalAction(f"REL {value} does not resolve")
            st.cur.rels.append((reltype, target))
        elif atype == CLOSE:
            cid = value
            if cid in st.ids:
                raise IllegalAction(f"duplicate claim id {cid}")
            c = Claim(cid, st.cur.text, st.cur.src, st.cur.key, list(st.cur.rels))
            st.claims.append(c)
            st.ids.add(cid)
            if c.key:
                st.seen_keys.add(c.key)
            st.cur = None
        return self.state

    # --- ergonomic entry point for a real model in the loop -----------------
    def emit(self, cid, text, src=None, key=None, rels=()):
        """Finalize one claim, or refuse. This is what a real model calls: it
        passes what it wants to assert, and the forcing function either returns
        the finalized Claim or raises until the model supplies what is missing.
        Atomic — on refusal the decoder state is left untouched."""
        st = self.state
        if not (text and text.strip()):
            raise IllegalAction("text required")
        if not (src and src.strip()):
            raise NeedsProvenance(f"claim {cid!r} needs a non-blank source")
        if key in st.seen_keys and not any(
                rt in RECONCILERS and tgt in st.ids for rt, tgt in rels):
            raise NeedsReconciliation(
                f"claim {cid!r} reuses key {key!r}; needs a reconciling edge "
                f"({'/'.join(sorted(RECONCILERS))}) to one of {sorted(st.ids)}")
        self.apply(START)
        self.apply(TEXT, text)
        if key:
            self.apply(KEY, key)
        for r in rels:
            self.apply(REL, r)
        self.apply(SRC, src)
        self.apply(CLOSE, cid)
        return st.output[-1]

    # --- driver -------------------------------------------------------------
    def generate(self, model):
        """Run a model to completion. `model.propose(state, legal)` must return
        an (atype, value) whose atype is in `legal` — that contract is the mask."""
        guard = 0
        while not self.state.done:
            guard += 1
            if guard > 10000:
                raise RuntimeError("generation did not terminate")
            legal = self.legal_types()
            atype, value = model.propose(self.state, legal)
            if atype not in legal:
                raise IllegalAction(
                    f"model proposed masked action {atype}; legal: {sorted(legal)}")
            self.apply(atype, value)
        return self.state.output
