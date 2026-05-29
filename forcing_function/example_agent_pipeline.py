"""Agent-pipeline handoff: a CONSUMER stage must trust a PRODUCER stage's
"I did it and it works" claims — but it was not in the room, and code can drift
between stages. This is the execution analogue of example_pipeline.py.

The point: the producer's confident report ("all three done") is, by itself,
unverifiable across the handoff (FINDINGS §9/§10: a confident "done" carries no
information about whether anything ran). Binding each claim to a receipt and
re-running it makes the handoff checkable — deterministically, at zero model
cost, pinpointing exactly which upstream claim regressed.

Run: PYTHONPATH=. python3 forcing_function/example_agent_pipeline.py
"""
import tempfile
import textwrap
from pathlib import Path

from forcing_function.verified import (
    ActionLedger, load_ledger, reverify, UnverifiedClaim, ReceiptMismatch)


def main():
    work = Path(tempfile.mkdtemp(prefix="agent_pipe_"))
    mod = work / "lib.py"
    ledger_path = work / "ledger.json"

    # ---- PRODUCER stage: implement, then claim each unit "works" -----------
    mod.write_text(textwrap.dedent("""
        def slugify(s):  return "-".join(s.lower().split())
        def add(a, b):   return a + b
        def clamp(x, lo, hi):  return max(lo, min(hi, x))
    """))
    tests = {
        "slugify": "from lib import slugify; assert slugify('Hello World')=='hello-world'",
        "add":     "from lib import add; assert add(2,3)==5",
        "clamp":   "from lib import clamp; assert clamp(5,0,3)==3 and clamp(-1,0,3)==0",
    }
    producer = ActionLedger(cwd=str(work))
    for cid, src in tests.items():
        # -B keeps the check hermetic (no .pyc cached between runs)
        producer.claim(cid, f"{cid}() works", check=["python3", "-B", "-c", src])
    producer.save(ledger_path)
    print(f"PRODUCER minted {len(producer.actions)} execution-backed claims -> {ledger_path.name}")
    print(f"  receipts: {producer.summary()}\n")

    # ---- DRIFT: a later edit silently breaks ONE unit ----------------------
    mod.write_text(textwrap.dedent("""
        def slugify(s):  return "-".join(s.lower().split())
        def add(a, b):   return a - b          # regression introduced here
        def clamp(x, lo, hi):  return max(lo, min(hi, x))
    """))
    print("DRIFT: lib.add was changed (+ became -). The producer already reported 'all done'.\n")

    # ---- CONSUMER stage: free-form trust vs. re-verified receipts ----------
    print("CONSUMER, trusting the producer's report: 'all three done' -> ships the break.\n")
    print("CONSUMER, re-verifying the receipts (loaded from disk, zero model tokens):")
    flagged = []
    for a in load_ledger(ledger_path):
        try:
            reverify(a, cwd=str(work))
            print(f"  OK     {a.id}: {a.assertion}")
        except ReceiptMismatch as e:
            flagged.append(a.id)
            print(f"  FLAGGED {a.id}: {str(e).splitlines()[0]}")
    print(f"\npinpointed regressed claim(s): {flagged}  | expected: ['add']")
    assert flagged == ["add"]
    print("PASS")


if __name__ == "__main__":
    main()
