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
import re
from dataclasses import asdict, dataclass, field

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


class CrossConsistency:
    """Bind a whole-value claim to an aggregation of the parts the producer ALSO
    emitted: e.g. an invoice `total` against `sum(line_items)`. Unlike Recompute
    it needs no reference fn — it catches a structure that disagrees with itself,
    which is the cheap, common case for emitted report/invoice fields. Trust root:
    internal arithmetic consistency of the emitted parts. `agg` defaults to sum."""
    kind = "cross"

    def __init__(self, claim, parts, whole, agg=sum):
        self.claim, self.parts, self.whole, self.agg = claim, parts, whole, agg

    def check(self):
        expected = self.agg(self.parts)
        ok = (expected == self.whole)
        return Receipt(self.kind, self.claim, ok,
                       "" if ok else f"whole {self.whole!r} != {self.agg.__name__}(parts) {expected!r}",
                       {"parts": self.parts, "whole": self.whole, "expected": expected,
                        "agg": getattr(self.agg, "__name__", "agg")})


class FileAbsent:
    """Bind an 'I removed/renamed every occurrence' claim to a filesystem scan: it
    records only if `pattern` appears ZERO times across `paths`. Trust root: the
    local file contents (the path list rides in the receipt, so reverify re-scans
    them — catching a regression that reintroduces the pattern). Defeats the
    'updated all the call-sites' confabulation.

    Honest scope: this is a regex/text scan (grep's exit codes are a foot-gun), NOT
    a semantic AST pass — a hit inside a comment or string still counts. Tighten the
    pattern (e.g. word boundaries) for call-site precision; the residue is the
    caller's to bind well, exactly the §14 adequacy residue."""
    kind = "file_absent"

    def __init__(self, claim, pattern, paths, flags=0):
        self.claim, self.pattern, self.paths, self.flags = claim, pattern, list(paths), flags

    def check(self):
        rx = re.compile(self.pattern, self.flags)
        hits, total = [], 0
        for p in self.paths:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    n = len(rx.findall(fh.read()))
            except FileNotFoundError:
                n = -1   # a missing scanned file is a defect, not a silent pass
            if n != 0:
                hits.append((p, n)); total += max(n, 1)
        ok = (total == 0)
        return Receipt(self.kind, self.claim, ok,
                       "" if ok else f"pattern {self.pattern!r} still present: {hits}",
                       {"pattern": self.pattern, "flags": self.flags,
                        "paths": self.paths, "hits": hits})


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

    def save(self, path):
        """Persist (cid, Receipt) pairs so a *later stage or another process* can
        re-verify them — the trust handoff verified.py already does for execution
        receipts, here for every kind. The receipt's `evidence` is what re-derives
        the check; the live roots that cannot be serialised (a Recompute's
        reference fn, a Quote's source text) are re-supplied at reverify time."""
        with open(path, "w") as fh:
            json.dump([{"cid": cid, **asdict(r)} for cid, r in self.receipts],
                      fh, indent=2)


def load_ledger(path):
    """Load (cid, Receipt) pairs written by Ledger.save()."""
    with open(path) as fh:
        raw = json.load(fh)
    return [(d["cid"], Receipt(d["kind"], d["claim"], d["ok"],
                               d.get("detail", ""), d.get("evidence", {})))
            for d in raw]


def reverify(receipt, *, source=None, fn=None, agg=None, cwd=None, timeout=120):
    """Independently re-derive a receipt. Fails closed. Re-supply the live root
    where it is code/text (a Quote's `source`, a Recompute's `fn`, a
    CrossConsistency's `agg` — default sum). `command`/`file_absent` carry their
    root (the command, the path list) in the receipt and need nothing re-supplied."""
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
    if receipt.kind == "cross":
        return (agg or sum)(e["parts"]) == e["whole"]
    if receipt.kind == "file_absent":
        rx = re.compile(e["pattern"], e.get("flags", 0))
        total = 0
        for p in e["paths"]:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    n = len(rx.findall(fh.read()))
            except FileNotFoundError:
                return False
            total += n
        return total == 0
    raise Unverified(f"unknown receipt kind {receipt.kind!r}")


def reverify_from_disk(path, *, fns=None, sources=None, aggs=None,
                       cwd=None, timeout=120):
    """Load a saved ledger and re-derive every receipt. Returns [(cid, bool)].

    Honest fail-closed contract: `command` and `file_absent` re-derive from stored
    evidence alone; `cross` re-derives with sum unless an `aggs[cid]` is supplied;
    but `recompute` and `quote` need a live root the JSON cannot hold — supply them
    per-claim via `fns` (cid -> reference fn) and `sources` (cid -> source text). A
    claim whose required root is missing re-derives to False, never silently True."""
    fns, sources, aggs = fns or {}, sources or {}, aggs or {}
    out = []
    for cid, r in load_ledger(path):
        try:
            ok = reverify(r, fn=fns.get(cid), source=sources.get(cid),
                          agg=aggs.get(cid), cwd=cwd, timeout=timeout)
        except Unverified:
            ok = False   # missing root for this kind => fail closed
        out.append((cid, ok))
    return out
