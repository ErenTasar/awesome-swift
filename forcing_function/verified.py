"""Execution ledger — bind an agent's completion claim to a real receipt.

The citation ledger asked "can a model invent a *source*?" and the answer turned
out to have no teeth: a strong model is already honest about text. This module
asks the question that *does* have teeth in agent pipelines:

    can an agent claim it DID or VERIFIED something it never actually ran?

That is not hypothetical. The sharpest artifact this project produced was exactly
it: an Opus agent wrote a script against a non-existent API (`gd.finalized()`,
`c.cid`) and confidently reported "runs cleanly" — it had never executed; a human
caught it only by running it by hand. Under pressure we reproduced the same class
on demand (a strong model citing a source for a value the source never states).
The model is the thing being *convincingly wrong*, so the model cannot be the
thing that checks it. Free-form "it works" is unverifiable by construction.

The fix is the same forcing-function philosophy, aimed correctly. A completion
claim is recordable ONLY if the ledger itself runs a check and the check's
outcome satisfies a predicate. An unbacked claim raises — there is no path to
record "done" on a confabulation. Each recorded claim carries a Receipt
(command, exit code, output digest, duration) that any later party can re-run
with `reverify()`.

Why this escapes the wall the citation ledger hit: its trust root is **local
re-execution** — the environment itself is the ground truth. No provider signing
key, no timestamp authority, no external root. The harness holds the root because
the harness can run the command.

Form is executed; intent is judged. A receipt, not a promise.
"""

import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass


# --- errors -----------------------------------------------------------------

class UnverifiedClaim(Exception):
    """A completion claim was not backed by a passing check; refused (fail-closed)."""


class ReceiptMismatch(Exception):
    """Re-running a recorded receipt no longer reproduces its outcome."""


# --- data -------------------------------------------------------------------

def digest(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


@dataclass
class Receipt:
    """The captured, reproducible evidence behind a claim. `cmd` keeps its
    original form (shell string or argv list) so it re-runs faithfully."""
    cmd: object
    exit_code: int
    output_digest: str       # sha256 of full combined stdout+stderr
    output_tail: str         # last chars, for human/predicate inspection
    duration_s: float


@dataclass
class Action:
    """A recorded, execution-backed completion claim."""
    id: str
    assertion: str
    receipt: Receipt


# --- runner (fail-closed) ---------------------------------------------------

_TAIL = 800


def _show(cmd):
    return cmd if isinstance(cmd, str) else " ".join(cmd)


def _run(cmd, cwd, timeout):
    """Run a check, always returning (Receipt, full_output). A check that cannot
    run — times out, binary missing — yields a failing receipt, never a pass.
    `cmd` is stored unchanged so the receipt re-runs exactly as recorded."""
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd,
                           timeout=timeout, capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired:
        out, code = f"[timeout after {timeout}s]", 124
    except FileNotFoundError as e:
        out, code = f"[command not found: {e}]", 127
    dur = round(time.monotonic() - start, 3)
    return Receipt(cmd, code, digest(out), out[-_TAIL:], dur), out


# --- the ledger -------------------------------------------------------------

class ActionLedger:
    """Records completion claims, each only if its check actually passes. The
    list of `actions` is, by construction, the set of claims that are backed by a
    real, reproducible receipt — the confabulated ones never got in."""

    def __init__(self, cwd=None, timeout=120):
        self.cwd = cwd
        self.timeout = timeout
        self.actions = []
        self._ids = set()

    def claim(self, cid, assertion, check, expect=None):
        """Record `assertion` only if `check` (a shell string or argv list) runs
        and `expect(receipt, output)` is true (default: exit code 0). Otherwise
        raise UnverifiedClaim and record nothing (atomic)."""
        if cid in self._ids:
            raise UnverifiedClaim(f"duplicate claim id {cid!r}")
        receipt, output = _run(check, self.cwd, self.timeout)
        ok = (receipt.exit_code == 0) if expect is None else bool(expect(receipt, output))
        if not ok:
            raise UnverifiedClaim(
                f"claim {cid!r} is not backed by its check.\n"
                f"  assertion: {assertion!r}\n"
                f"  check:     {_show(receipt.cmd)!r} -> exit {receipt.exit_code}\n"
                f"  output:    ...{receipt.output_tail.strip()[-400:]}")
        action = Action(cid, assertion, receipt)
        self.actions.append(action)
        self._ids.add(cid)
        return action

    def summary(self):
        return [(a.id, a.assertion, a.receipt.exit_code) for a in self.actions]

    def save(self, path):
        """Persist the receipts so a *later stage or another process* can
        re-verify them. This is what makes a trust handoff real: the producer
        writes the ledger, the consumer loads and re-runs it."""
        with open(path, "w") as fh:
            json.dump([asdict(a) for a in self.actions], fh, indent=2)


def load_ledger(path):
    """Load recorded actions written by ActionLedger.save()."""
    with open(path) as fh:
        raw = json.load(fh)
    return [Action(a["id"], a["assertion"], Receipt(**a["receipt"])) for a in raw]


def reverify(action, cwd=None, timeout=120, require_same_output=False):
    """Independently re-run a recorded action's check. Fails closed: a different
    exit code (or, if required, a changed output digest) means the claim no
    longer holds — the work regressed or the receipt was fabricated."""
    receipt, _ = _run(action.receipt.cmd, cwd, timeout)
    if receipt.exit_code != action.receipt.exit_code:
        raise ReceiptMismatch(
            f"claim {action.id!r}: check {_show(receipt.cmd)!r} now exits "
            f"{receipt.exit_code}, was {action.receipt.exit_code}")
    if require_same_output and receipt.output_digest != action.receipt.output_digest:
        raise ReceiptMismatch(
            f"claim {action.id!r}: output of {_show(receipt.cmd)!r} changed since recorded")
    return True


# --- CLI: make completion claims and re-verification usable from a shell ----

def _cli(argv):
    """
      verified claim <id> <assertion> <ledger.json> -- <check cmd...>
          run <check>; append a receipt to <ledger.json> iff it passes.
      verified verify <ledger.json>
          re-run every recorded receipt; exit 1 if any fails.
    """
    if not argv or argv[0] not in ("claim", "verify"):
        print(_cli.__doc__); return 2
    if argv[0] == "claim":
        sep = argv.index("--")
        cid, assertion, path = argv[1], argv[2], argv[3]
        check = argv[sep + 1:]
        try:
            led = ActionLedger()
            led.actions = load_ledger(path)
            led._ids = {a.id for a in led.actions}
        except FileNotFoundError:
            led = ActionLedger()
        try:
            a = led.claim(cid, assertion, check)
        except UnverifiedClaim as e:
            print(f"REFUSED: {e}"); return 1
        led.save(path)
        print(f"recorded {a.id!r}: exit={a.receipt.exit_code} "
              f"digest={a.receipt.output_digest[:12]}")
        return 0
    # verify
    bad = []
    for a in load_ledger(argv[1]):
        try:
            reverify(a)
            print(f"  OK     {a.id}: {a.assertion}")
        except ReceiptMismatch as e:
            bad.append(a.id); print(f"  FAILED {a.id}: {e}")
    print(f"{'FAIL' if bad else 'PASS'}: {len(bad)} regressed claim(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
