"""Citation ledger — the API-only core of the forcing function.

Scope, set deliberately: this targets models reached through an API (no logit
access). The earlier token-mask machine (constrained_decode.py) was the software
analogue of masking logits — but with no logits to mask it was just validation in
disguise, and A/B evals showed cite() gives the identical guarantee in a fraction
of the code. So that machine, its grammar and its demos are gone. What remains is
the part the evals actually showed value from:

  1. MECHANICAL PROVENANCE INTEGRITY — finite and sound:
       resolvable source   src must be a SourcePool id        -> no invented source
       verbatim quote      quote is an exact substring of src -> no fabricated quote
       tamper-evident      sha256 fingerprint (fail-closed)   -> later edits detected
       trusted origin      link in an allowlist (fail-closed) -> named, accountable root
       extractive (opt.)   claim text == quote                -> no paraphrase channel

  2. RECONCILIATION — a claim that reuses a prior `key` (i.e. conflicts) cannot be
     recorded without an explicit reconciling edge (contradicts/supersedes/
     refines) to an existing claim. You cannot silently store two conflicting facts.

  3. SEMANTIC FAITHFULNESS — one fallible judge, with FULL CONTEXT:
       judge(claim, quote, source) decides whether the quote, seen inside the
       whole source, actually supports the claim. Omission, cherry-picking,
       relation reversal, polarity — all of it lives here, in a single check.
       No wordlists, no sentence regex.

Form is provable; meaning is judged. well-formedness, not truth.
"""

import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlparse

RECONCILERS = {"contradicts", "supersedes", "refines"}


# --- errors -----------------------------------------------------------------

class CiteError(Exception):
    """Base: a claim could not be recorded as cited."""


class UnresolvableSource(CiteError):
    """The cited source id is not in the pool (invented source)."""


class FabricatedQuote(CiteError):
    """The quote is not an exact substring of the cited source (or, in extractive
    mode, the claim is not the quote verbatim)."""


class UntrustedSource(CiteError):
    """A trusted link was required but the source has none, the pool declares no
    allowlist, or the link's origin is not on it."""


class NeedsReconciliation(CiteError):
    """A claim reuses a prior key but carries no reconciling edge to an existing
    claim, or its edge does not resolve / the id is duplicated."""


class UnfaithfulCitation(CiteError):
    """The (fallible) judge ruled the quote, in context, does not support the claim."""


class TamperedSource(Exception):
    """Re-verification failed: the source changed, vanished, or is unverifiable."""


# --- data -------------------------------------------------------------------

@dataclass
class Claim:
    """A recorded, cited claim."""
    id: str
    text: str
    src: str
    quote: str
    key: str = None
    rels: list = field(default_factory=list)   # list of (reltype, target_id)
    src_hash: str = None
    uri: str = None


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _domain(uri):
    return (urlparse(uri).hostname or "").lower()


class SourcePool:
    """The closed set of sources a model may cite. Each is fingerprinted (so later
    edits are detectable) and may carry a reference `uri`. `trusted_domains` is the
    named, accountable trust root: when set, citing is limited to sources whose
    link origin is on the allowlist."""

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


# --- the ledger -------------------------------------------------------------

class GroundedDecoder:
    """The single, non-bypassable citation surface. It owns a pool and the running
    reconciliation state, and exposes only `cite()` — there is no ungrounded path
    to forget. Each cite() either records a finalized Claim or refuses; on refusal
    no state changes (atomic)."""

    def __init__(self, pool, judge=None, extractive=False,
                 require_trusted_link=False):
        self.pool = pool
        self.judge = judge
        self.extractive = extractive
        self.require_trusted_link = require_trusted_link
        self.claims = []
        self._ids = set()
        self._seen_keys = set()

    def cite(self, cid, text, src, quote, key=None, rels=()):
        pool = self.pool
        # --- mechanical provenance integrity ---
        body = pool.text(src)
        if body is None:
            raise UnresolvableSource(
                f"src {src!r} is not in the source pool {sorted(pool.sources)}")
        if self.require_trusted_link:
            uri = pool.uri(src)
            if not uri:
                raise UntrustedSource(f"src {src!r} has no reference link")
            if pool.trusted_domains is None:                      # fail closed
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
        if self.extractive and text.strip() != quote.strip():
            raise FabricatedQuote(
                f"extractive: claim {cid!r} must be the quote verbatim, "
                f"got {text!r} != {quote!r}")
        # --- structural integrity: ids and reconciliation ---
        if cid in self._ids:
            raise NeedsReconciliation(f"duplicate claim id {cid!r}")
        for reltype, target in rels:
            if reltype not in RECONCILERS or target not in self._ids:
                raise NeedsReconciliation(
                    f"edge {(reltype, target)!r} does not resolve to an existing "
                    f"claim {sorted(self._ids)}")
        if key in self._seen_keys and not any(
                rt in RECONCILERS and tgt in self._ids for rt, tgt in rels):
            raise NeedsReconciliation(
                f"claim {cid!r} reuses key {key!r}; needs a reconciling edge "
                f"({'/'.join(sorted(RECONCILERS))}) to one of {sorted(self._ids)}")
        # --- semantic faithfulness: one judge, full source as context ---
        if self.judge is not None and not self.judge(text, quote, body):
            raise UnfaithfulCitation(
                f"claim {cid!r} is not supported by its quote in context "
                f"(judge rejected)")
        c = Claim(id=cid, text=text, src=src, quote=quote, key=key,
                  rels=list(rels), src_hash=pool.hash(src), uri=pool.uri(src))
        self.claims.append(c)
        self._ids.add(cid)
        if key:
            self._seen_keys.add(key)
        return c


def reverify(pool, claim, require_trusted_link=False):
    """Independent re-check of a recorded claim against the (possibly reloaded)
    pool. Fails closed: a claim with no recorded hash is unverifiable, not valid."""
    body = pool.text(claim.src)
    if body is None:
        raise TamperedSource(f"source {claim.src!r} vanished from the pool")
    if claim.src_hash is None:                                    # fail closed
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
