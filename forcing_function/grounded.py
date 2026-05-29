"""Grounding layer: push the source from 'present' to 'resolvable + verbatim +
word-bounded', and the pool from 'trusted' to 'tamper-evident'.

The base forcing function (constrained_decode.py) guarantees a claim carries a
non-blank source — but a model under pressure invents one ("general
knowledge..."). This layer hardens that, mechanically where it can and honestly
flagging where it cannot:

  Tier 1  RESOLVABILITY    src must be an id in a pre-supplied SourcePool.
                           => an invented source is impossible by construction.
  Tier 2  VERBATIM QUOTE   the claim carries a `quote` that appears verbatim in
                           that source.
                           => a fabricated quote is impossible (exact substring).
  Tier 2b WHOLE SENTENCE   the quote must be a run of whole sentences.
                           => slicing a sub-span to drop a negation is impossible
                              ("...not guilty..." -> "guilty...").
  Tier 2c GROUNDED WORDS   every content word in the claim must occur in the
                           quote (stopwords/negations excluded).
                           => the claim cannot introduce an entity, number or
                              predicate absent from the evidence; this kills the
                              "real but irrelevant quote" attack mechanically,
                              the case previously thought to need a judge.
  Tier 2d NEGATION PARITY  the claim's negation cues must match the quote's.
                           => you cannot reuse the source's own words to assert
                              the opposite polarity ("infection found" from
                              "no infection found").
  Tier 3  FAITHFULNESS     does the (real, word-bounded) quote actually entail
                           the claim? Still semantic. Delegated to a fallible
                           `judge`. Tiers 2c/2d shrink its job to the genuinely
                           hard residue (correct relation among shared words);
                           they do not eliminate it.

Honest limits that remain:
  * 2c/2d are NECESSARY, not SUFFICIENT, conditions for faithfulness: a claim
    built only from the quote's words, with matching polarity, can still misorder
    a relation. That residue is the judge's, and the judge is fallible.
  * Pool poisoning: provenance is only as honest as the pool's contents. We make
    it TAMPER-EVIDENT (each source is fingerprinted; a claim records src_hash, so
    later edits are detectable and a claim can be re-verified against the source).
    We cannot make it TRUSTWORTHY here — that needs an external trust anchor
    (sources signed by an accountable issuer, re-fetched and re-checked at audit
    time). Tamper-evidence moves the trust to a named, verifiable root; it does
    not conjure trust from nothing.
"""

import hashlib
import re

from forcing_function.constrained_decode import (
    ForcingDecoder, NeedsProvenance, IllegalAction)

_SENTENCE = re.compile(r"\S.*?[.!?](?=\s|$)", re.S)

# Function words and negation cues. Negations are kept OUT of the content-word
# set on purpose: dropping/adding a negation must be caught by polarity (2d),
# not silently allowed by word-containment (2c).
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "of",
    "to", "in", "on", "at", "for", "and", "or", "as", "that", "this", "it",
    "its", "by", "with", "from", "has", "have", "had", "will", "would", "can",
    "could", "all", "any", "some", "so", "but", "if", "then", "than", "into",
    "over", "under", "after", "before", "they", "he", "she", "we", "you", "i",
}
_NEG = {
    "no", "not", "never", "none", "without", "cannot", "nor", "neither",
    "denies", "denied", "deny", "absence", "absent", "negative", "ruled",
    "excludes", "excluded", "lacks", "lacking", "fails", "failed", "unable",
}


def _tokens(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def _content_words(s):
    return {t for t in _tokens(s) if t not in _STOP and t not in _NEG}


def _negations(s):
    toks = set(_tokens(s))
    cues = {t for t in toks if t in _NEG}
    if "n't" in s.lower() or "n’t" in s.lower():
        cues.add("nt")
    return cues


def _sentence_run(body, quote):
    """True iff `quote` is one or more consecutive whole sentences of `body`."""
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
    """Tier 2 / 2b: the quote is not a verbatim whole-sentence span of the src."""


class UngroundedClaim(IllegalAction):
    """Tier 2c/2d: the claim uses words or polarity not present in the quote."""


class UnfaithfulCitation(IllegalAction):
    """Tier 3: the (fallible) judge ruled the quote does not support the claim."""


class TamperedSource(Exception):
    """Re-verification: the source text no longer matches the recorded hash."""


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourcePool:
    """The closed set of sources a model is allowed to cite, each fingerprinted
    so tampering is detectable. A model cannot cite anything outside it, so
    provenance cannot be invented; and a later edit to a source is detectable via
    its hash."""

    def __init__(self, sources):
        self.sources = dict(sources)        # id -> full source text

    def text(self, sid):
        return self.sources.get(sid)

    def hash(self, sid):
        body = self.sources.get(sid)
        return None if body is None else fingerprint(body)


def emit_grounded(d, pool, cid, text, src, quote, key=None, rels=(), judge=None,
                  whole_sentence=True, grounded_words=True, negation_parity=True):
    """Emit a claim only if its source resolves, its quote is verbatim (and, by
    default, whole-sentence and word-bounded), polarity matches, and an optional
    judge accepts. Atomic: every check runs before the underlying emit().

    Flags trade safety for flexibility (all default to the safe setting):
      whole_sentence   quote must be whole sentence(s)        (blocks negation-drop)
      grounded_words   claim's content words must be in quote (blocks new facts /
                       irrelevant quotes)
      negation_parity  claim & quote negation cues must match (blocks polarity flip)
    """
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
    # Tier 2c — grounded words: the claim cannot say more than the quote does.
    if grounded_words:
        missing = _content_words(text) - _content_words(quote)
        if missing:
            raise UngroundedClaim(
                f"claim {cid!r} uses words absent from its quote: {sorted(missing)}"
                f" (it may only assert what the quote's words support)")
    # Tier 2d — negation parity: same polarity as the quote.
    if negation_parity and bool(_negations(text)) != bool(_negations(quote)):
        raise UngroundedClaim(
            f"claim {cid!r} negation does not match its quote "
            f"(claim={sorted(_negations(text))} quote={sorted(_negations(quote))})")
    # Tier 3 — faithful: semantic, hence a fallible judge, not a guarantee.
    if judge is not None and not judge(text, quote):
        raise UnfaithfulCitation(
            f"claim {cid!r} is not supported by its quote (judge rejected)")
    c = d.emit(cid=cid, text=text, src=src, key=key, rels=rels)
    c.quote = quote
    c.src_hash = pool.hash(src)
    return c


def reverify(pool, claim):
    """Independent re-check of a finalized claim against the (possibly reloaded)
    pool: the source must still exist, hash to the recorded fingerprint, and
    still contain the quote. Detects pool poisoning / tampering after the fact."""
    body = pool.text(claim.src)
    if body is None:
        raise TamperedSource(f"source {claim.src!r} vanished from the pool")
    if claim.src_hash is not None and pool.hash(claim.src) != claim.src_hash:
        raise TamperedSource(f"source {claim.src!r} changed since the claim was made")
    if claim.quote and claim.quote not in body:
        raise TamperedSource(f"quote no longer present in source {claim.src!r}")
    return True
