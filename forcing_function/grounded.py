"""Grounding layer — two primitives, nothing in between.

The earlier design grew a middle layer of half-mechanical heuristics
(whole-sentence, grounded-words, negation-parity). A pentest showed each one was
both *unsound* (bypassable: abbreviation sentence-splits, qualifier omission,
off-list polarity words) and *incomplete* (the residue is endless). Chasing
meaning with wordlists is a losing, never-ending game. So that middle is gone.
What is left is two clean primitives:

  1. MECHANICAL PROVENANCE INTEGRITY — finite and sound:
       resolvable source   src must be a SourcePool id        -> no invented source
       verbatim quote      quote is an exact substring of src -> no fabricated quote
       tamper-evident      sha256 fingerprint (fail-closed)   -> later edits detected
       trusted origin      link in an allowlist (fail-closed) -> named, accountable root
       extractive (opt.)   claim text == quote                -> no paraphrase channel

  2. SEMANTIC FAITHFULNESS — one fallible judge, with FULL CONTEXT:
       judge(claim, quote, source) decides whether the quote, *seen inside the
       whole source*, actually supports the claim. Omission, cherry-picking,
       relation reversal, polarity — all of it lives here, in a single check that
       sees the entire source. No wordlists, no sentence regex.

Form is provable; meaning is judged. well-formedness, not truth.
"""

import hashlib
from urllib.parse import urlparse

from forcing_function.constrained_decode import (
    ForcingDecoder, NeedsProvenance, IllegalAction)


class UnresolvableSource(NeedsProvenance):
    """The cited source id is not in the pool (invented source)."""


class FabricatedQuote(NeedsProvenance):
    """The quote is not an exact substring of the cited source (or, in extractive
    mode, the claim is not the quote verbatim)."""


class UntrustedSource(NeedsProvenance):
    """A trusted link was required but the source has none, the pool declares no
    allowlist, or the link's origin is not on it."""


class UnfaithfulCitation(IllegalAction):
    """The (fallible) judge ruled the quote, in context, does not support the claim."""


class TamperedSource(Exception):
    """Re-verification failed: the source changed, vanished, or is unverifiable."""


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _domain(uri):
    return (urlparse(uri).hostname or "").lower()


class SourcePool:
    """The closed set of sources a model may cite. Each is fingerprinted (so
    later edits are detectable) and may carry a reference `uri`. `trusted_domains`
    is the named, accountable trust root: when set, citing is limited to sources
    whose link origin is on the allowlist."""

    def __init__(self, sources, uris=None, trusted_domains=None):
        self.sources = dict(sources)
        self.uris = dict(uris or {})
        self.trusted_domains = (set(d.lower() for d in trusted_domains)
                                if trusted_domains is not None else None)

    def text(self, sid):
        return self.sources.get(sid)

    def uri(self, sid):
        return self.uris.get(sid)

    def hash(self, sid):
        body = self.sources.get(sid)
        return None if body is None else fingerprint(body)


def emit_grounded(d, pool, cid, text, src, quote, key=None, rels=(),
                  judge=None, extractive=False, require_trusted_link=False):
    """Finalize a cited claim, or refuse. Mechanical integrity is enforced
    unconditionally; meaning is left to `judge(claim, quote, source)` if supplied.
    Atomic: every check runs before the underlying emit(), so a refusal leaves the
    decoder state untouched.

      extractive            require the claim text to BE the quote verbatim
                            (removes the paraphrase channel entirely).
      require_trusted_link  the source must carry a link whose origin is on the
                            pool's trusted-domain allowlist; fails closed if the
                            allowlist is unset.
    """
    # --- mechanical provenance integrity ---
    body = pool.text(src)
    if body is None:
        raise UnresolvableSource(
            f"src {src!r} is not in the source pool {sorted(pool.sources)}")
    if require_trusted_link:
        uri = pool.uri(src)
        if not uri:
            raise UntrustedSource(f"src {src!r} has no reference link")
        if pool.trusted_domains is None:                       # fail closed
            raise UntrustedSource(
                "require_trusted_link is set but the pool declares no "
                "trusted_domains; refusing rather than trusting any origin")
        if _domain(uri) not in pool.trusted_domains:
            raise UntrustedSource(
                f"link {uri!r} (origin {_domain(uri)!r}) is not in the trusted "
                f"allowlist {sorted(pool.trusted_domains)}")
    if not (quote and quote.strip()):
        raise FabricatedQuote(f"claim {cid!r} needs a verbatim quote from {src!r}")
    if quote not in body:
        raise FabricatedQuote(
            f"quote {quote!r} does not appear verbatim in source {src!r}")
    if extractive and text.strip() != quote.strip():
        raise FabricatedQuote(
            f"extractive: claim {cid!r} must be the quote verbatim, "
            f"got {text!r} != {quote!r}")
    # --- semantic faithfulness: one judge, full source as context ---
    if judge is not None and not judge(text, quote, body):
        raise UnfaithfulCitation(
            f"claim {cid!r} is not supported by its quote in context (judge rejected)")
    c = d.emit(cid=cid, text=text, src=src, key=key, rels=rels)
    c.quote = quote
    c.src_hash = pool.hash(src)
    c.uri = pool.uri(src)
    return c


def reverify(pool, claim, require_trusted_link=False):
    """Independent re-check of a finalized claim against the (possibly reloaded)
    pool. Fails closed: a claim with no recorded hash is unverifiable, not valid."""
    body = pool.text(claim.src)
    if body is None:
        raise TamperedSource(f"source {claim.src!r} vanished from the pool")
    if claim.src_hash is None:                                 # fail closed
        raise TamperedSource(
            f"claim {claim.id!r} has no recorded src_hash; unverifiable")
    if pool.hash(claim.src) != claim.src_hash:
        raise TamperedSource(f"source {claim.src!r} changed since the claim was made")
    if claim.quote and claim.quote not in body:
        raise TamperedSource(f"quote no longer present in source {claim.src!r}")
    if require_trusted_link:
        uri = pool.uri(claim.src)
        if (not uri or pool.trusted_domains is None
                or _domain(uri) not in pool.trusted_domains):
            raise TamperedSource(
                f"source {claim.src!r} no longer has a trusted link")
    return True


class GroundedDecoder:
    """The non-bypassable citation surface. It owns a pool and exposes only
    `cite()`, so there is no ungrounded `emit()`/`apply()` path to forget — the
    integrity checks are not optional. Use this, not a bare ForcingDecoder, when
    every claim must be cited."""

    def __init__(self, pool, judge=None, extractive=False,
                 require_trusted_link=False):
        self._d = ForcingDecoder()
        self._pool = pool
        self._judge = judge
        self._extractive = extractive
        self._require_trusted_link = require_trusted_link

    def cite(self, cid, text, src, quote, key=None, rels=()):
        return emit_grounded(
            self._d, self._pool, cid, text, src, quote, key=key, rels=rels,
            judge=self._judge, extractive=self._extractive,
            require_trusted_link=self._require_trusted_link)

    @property
    def claims(self):
        return self._d.state.output
