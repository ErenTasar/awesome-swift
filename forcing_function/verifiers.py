"""Generalised claim-to-receipt verification.

The whole project is one pattern: a claim is recordable only if a model-INDEPENDENT,
reproducible check produces a passing Receipt. grounded.cite() (a verbatim-quote
receipt) and verified.ActionLedger.claim() (an execution receipt) are two
instances. This names the pattern as a pluggable `Verifier` and adds the receipt
type the channel-suppression study (FINDINGS §12/§13) showed is most needed:
RECOMPUTE — bind a computed value (a charge amount, a count, a total) to an
independent reference computation, so a confidently-wrong structured-output field
cannot be recorded.

Each Verifier exposes `check() -> Receipt`. `reverify(receipt, ...)` re-derives the
receipt later (re-running the command, re-checking the substring, re-computing the
value) so a downstream stage can confirm it without trusting the producer.

Trust root per kind is explicit and local (re-execution / the source text / a
reference function) — none requires a provider key or external authority.
"""

import hashlib
import json
from dataclasses import dataclass, field

from forcing_function.verified import _run, _show, digest  # reuse the runner


def _hash(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class Unverified(Exception):
    """A claim's verifier did not produce a passing receipt; refused (fail-closed)."""


@dataclass
class Receipt:
    kind: str           # which verifier produced it
    claim: str          # the natural-language claim being checked
    ok: bool
    detail: str = ""    # why it failed (empty on success)
    evidence: dict = field(default_factory=dict)   # reproducible inputs/outputs


# --- verifiers: each independent of the model that made the claim -----------

class Recompute:
    """Bind a computed value to an independent reference computation. Defeats the
    §13 failure: an emitted total/count/amount is recorded only if it equals the
    value re-derived from the same inputs by `fn`. Trust root: the reference fn."""
    kind = "recompute"

    def __init__(self, claim, fn, inputs, claimed):
        self.claim, self.fn, self.inputs, self.claimed = claim, fn, inputs, claimed

    def check(self):
        expected = self.fn(**self.inputs)
        ok = (expected == self.claimed)
        return Receipt(self.kind, self.claim, ok,
                       "" if ok else f"claimed {self.claimed!r} != recomputed {expected!r}",
                       {"inputs": self.inputs, "inputs_hash": _hash(self.inputs),
                        "claimed": self.claimed, "expected": expected})


class Command:
    """Bind a 'done/works/passes' claim to a real execution. Trust root: local
    re-execution. (The verified.ActionLedger core, as a verifier.)"""
    kind = "command"

    def __init__(self, claim, cmd, expect=None, cwd=None, timeout=120):
        self.claim, self.cmd, self.expect = claim, cmd, expect
        self.cwd, self.timeout = cwd, timeout

    def check(self):
        r, out = _run(self.cmd, self.cwd, self.timeout)
        ok = (r.exit_code == 0) if self.expect is None else bool(self.expect(r, out))
        return Receipt(self.kind, self.claim, ok,
                       "" if ok else f"{_show(r.cmd)!r} -> exit {r.exit_code}: {r.output_tail.strip()[-200:]}",
                       {"cmd": r.cmd, "exit": r.exit_code, "output_digest": r.output_digest})


class Quote:
    """Bind a factual claim to a verbatim substring of a named source. Trust root:
    the source text. (The grounded.cite() core, as a verifier.)"""
    kind = "quote"

    def __init__(self, claim, source, quote):
        self.claim, self.source, self.quote = claim, source, quote

    def check(self):
        ok = bool(self.quote and self.quote.strip()) and self.quote in self.source
        return Receipt(self.kind, self.claim, ok,
                       "" if ok else f"quote {self.quote!r} not a verbatim substring of source",
                       {"quote": self.quote, "source_digest": digest(self.source)})


# --- the ledger: record only what verifies -----------------------------------

class Ledger:
    """Records (cid, Receipt) pairs, each only if its verifier passed. The list of
    receipts is, by construction, the set of claims backed by a reproducible,
    model-independent check."""

    def __init__(self):
        self.receipts = []
        self._ids = set()

    def record(self, cid, verifier):
        if cid in self._ids:
            raise Unverified(f"duplicate claim id {cid!r}")
        r = verifier.check()
        if not r.ok:
            raise Unverified(f"claim {cid!r} not backed ({r.kind}): {r.detail}")
        self.receipts.append((cid, r))
        self._ids.add(cid)
        return r

    def summary(self):
        return [(cid, r.kind, r.claim) for cid, r in self.receipts]


def reverify(receipt, *, source=None, fn=None, cwd=None, timeout=120):
    """Independently re-derive a receipt. Fails closed. Re-supply the live root
    where it is code/text (a Quote's `source`, a Recompute's `fn`)."""
    e = receipt.evidence
    if receipt.kind == "command":
        r, _ = _run(e["cmd"], cwd, timeout)
        return r.exit_code == e["exit"]
    if receipt.kind == "quote":
        if source is None:
            raise Unverified("reverify(quote) needs the source to re-check against")
        return digest(source) == e["source_digest"] and e["quote"] in source
    if receipt.kind == "recompute":
        if fn is None:
            raise Unverified("reverify(recompute) needs the reference fn")
        return fn(**e["inputs"]) == e["claimed"]
    raise Unverified(f"unknown receipt kind {receipt.kind!r}")
