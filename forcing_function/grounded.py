"""Grounding layer: push the source from 'present' to 'resolvable + verbatim'.

The base forcing function (constrained_decode.py) guarantees a claim carries a
non-blank source — but a model under pressure will invent one ("general
knowledge..."). This layer closes that, in two tiers that are *mechanically*
enforceable, plus a third that is honestly not:

  Tier 1  RESOLVABILITY   src must be an id in a pre-supplied SourcePool.
                          => an invented source is impossible by construction.
  Tier 2  VERBATIM QUOTE  the claim must carry a `quote` that appears verbatim
                          in that source's text.
                          => a fabricated quote is impossible (exact substring).
  Tier 3  FAITHFULNESS    does the (real) quote actually support the claim?
                          This is semantic. No mask or string match can decide
                          it. It is delegated to a `judge` callable — which is a
                          fallible model, so this tier *reduces* bad citations,
                          it does not make them impossible. Stated plainly so the
                          guarantee is not oversold.

What this still cannot stop: citing a real source and a real-but-irrelevant
quote from it, or distorting the quote's meaning in the claim text. Only the
(fallible) judge addresses those, and only as well as the judge is calibrated.
"""

from forcing_function.constrained_decode import (
    ForcingDecoder, NeedsProvenance, IllegalAction)


class UnresolvableSource(NeedsProvenance):
    """Tier 1: the cited source id is not in the pool (invented source)."""


class FabricatedQuote(NeedsProvenance):
    """Tier 2: the quote does not appear verbatim in the cited source."""


class UnfaithfulCitation(IllegalAction):
    """Tier 3: the (fallible) judge ruled the quote does not support the claim."""


class SourcePool:
    """The closed set of sources a model is allowed to cite. A model cannot cite
    anything outside it, so provenance can no longer be invented."""

    def __init__(self, sources):
        self.sources = dict(sources)        # id -> full source text

    def text(self, sid):
        return self.sources.get(sid)


def emit_grounded(d, pool, cid, text, src, quote, key=None, rels=(), judge=None):
    """Like ForcingDecoder.emit, but the source must resolve to `pool` and the
    `quote` must be a verbatim span of it. Optional `judge(claim_text, quote) ->
    bool` adds the (fallible) faithfulness gate. Atomic: refusal leaves state
    untouched, because every check runs before the underlying emit()."""
    # Tier 1 — resolvable: invented sources are impossible.
    body = pool.text(src)
    if body is None:
        raise UnresolvableSource(
            f"src {src!r} is not in the source pool {sorted(pool.sources)}")
    # Tier 2 — verbatim: fabricated quotes are impossible.
    if not (quote and quote.strip()):
        raise FabricatedQuote(f"claim {cid!r} needs a verbatim quote from {src!r}")
    if quote not in body:
        raise FabricatedQuote(
            f"quote {quote!r} does not appear verbatim in source {src!r}")
    # Tier 3 — faithful: semantic, hence a fallible judge, not a guarantee.
    if judge is not None and not judge(text, quote):
        raise UnfaithfulCitation(
            f"claim {cid!r} is not supported by its quote (judge rejected)")
    c = d.emit(cid=cid, text=text, src=src, key=key, rels=rels)
    c.quote = quote
    return c
