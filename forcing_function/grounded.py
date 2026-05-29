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
*whole sentence* from it, or distorting its meaning in the claim's own wording.
Only the (fallible) judge addresses those, and only as well as it is calibrated.
(The whole-sentence rule below does close the sharpest mechanical trick a
red-team found: quoting a verbatim sub-span that drops a leading negation.)
"""

import re

from forcing_function.constrained_decode import (
    ForcingDecoder, NeedsProvenance, IllegalAction)

# A quote, by default, must be a run of WHOLE sentences from the source. This
# closes the sharpest verbatim-but-deceptive trick: slicing a sub-span that drops
# a leading negation ("...not guilty on all counts." -> "guilty on all counts.").
# An arbitrary substring is still verbatim, so without this an attacker can
# reverse the source's meaning while passing an exact-match check.
_SENTENCE = re.compile(r"\S.*?[.!?](?=\s|$)", re.S)


def _sentence_run(body, quote):
    """True iff `quote` starts at a sentence start and ends at a sentence end in
    `body` (one or more consecutive whole sentences)."""
    spans = [(m.start(), m.end()) for m in _SENTENCE.finditer(body)]
    starts = {s for s, _ in spans}
    ends = {e for _, e in spans}
    idx = body.find(quote)
    while idx != -1:
        if idx in starts and idx + len(quote) in ends:
            return True
        idx = body.find(quote, idx + 1)
    return False


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


def emit_grounded(d, pool, cid, text, src, quote, key=None, rels=(), judge=None,
                  whole_sentence=True):
    """Like ForcingDecoder.emit, but the source must resolve to `pool` and the
    `quote` must be a verbatim span of it. Optional `judge(claim_text, quote) ->
    bool` adds the (fallible) faithfulness gate. Atomic: refusal leaves state
    untouched, because every check runs before the underlying emit().

    `whole_sentence` (default True) additionally requires the quote to be a run
    of whole sentences, so a sub-span cannot drop a leading negation. Set it
    False to allow mid-sentence fragments — more flexible, but it re-opens the
    sub-span distortion trick, so only the judge stands between you and it."""
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
    # Tier 2b — whole-sentence: a sub-span cannot strip a negation or context.
    if whole_sentence and not _sentence_run(body, quote):
        raise FabricatedQuote(
            f"quote {quote!r} is a partial span; it must be whole sentence(s) "
            f"of source {src!r} (else a sub-span could reverse its meaning)")
    # Tier 3 — faithful: semantic, hence a fallible judge, not a guarantee.
    if judge is not None and not judge(text, quote):
        raise UnfaithfulCitation(
            f"claim {cid!r} is not supported by its quote (judge rejected)")
    c = d.emit(cid=cid, text=text, src=src, key=key, rels=rels)
    c.quote = quote
    return c
