"""Reproduce the project's sharpest artifact, then catch it automatically.

The story (real, from this project's own history): an agent wrote a script
against a *non-existent* API and reported "runs cleanly." It had never run. Here
we recreate that exact situation and show the execution ledger refusing to record
the false completion claim — deterministically, with zero model tokens, where a
free-form "it works" sailed through.

Run: PYTHONPATH=. python3 forcing_function/verified_demo.py
"""
import tempfile
import textwrap
from pathlib import Path

from forcing_function.verified import ActionLedger, reverify, UnverifiedClaim


def main():
    work = Path(tempfile.mkdtemp(prefix="ledger_demo_"))

    # The module under test: it has compute(), but NO finalize().
    (work / "widget.py").write_text(textwrap.dedent("""
        def compute():
            return 42
    """))

    # The agent's "smoke test" — written against a method that does not exist,
    # exactly like the gd.finalized() artifact.
    (work / "smoke.py").write_text(textwrap.dedent("""
        import widget
        print("result:", widget.finalize())   # AttributeError: no such function
    """))

    print(f"workdir: {work}\n")

    # --- FREE-FORM: the agent just asserts success (the status quo) ----------
    free_form_report = "I ran smoke.py and it runs cleanly. Task complete."
    print("FREE-FORM agent report (trusted today):")
    print(f"  > {free_form_report}")
    print("  -> recorded as 'done'. Nobody ran anything. This is the bug.\n")

    # --- LEDGER: the same claim must bind to a real execution ----------------
    led = ActionLedger(cwd=str(work))
    print("LEDGER: same claim, but it must bind to a receipt:")
    try:
        led.claim("smoke", "smoke.py runs cleanly", check="python3 smoke.py")
        print("  -> recorded (unexpected!)")
    except UnverifiedClaim as e:
        print("  -> REFUSED automatically:")
        for line in str(e).splitlines():
            print(f"     {line}")
    print(f"  recorded actions: {led.summary()}   (the confabulation never got in)\n")

    # --- the agent actually fixes the code, then the claim can be made -------
    (work / "smoke.py").write_text(textwrap.dedent("""
        import widget
        assert widget.compute() == 42
        print("result:", widget.compute())
    """))
    a = led.claim("smoke", "smoke.py runs cleanly", check="python3 smoke.py")
    print("After a real fix, the claim binds to a receipt:")
    print(f"  {a.id}: exit={a.receipt.exit_code} digest={a.receipt.output_digest[:12]}… "
          f"({a.receipt.duration_s}s)")
    print(f"  recorded actions: {led.summary()}")

    # --- independent re-verification (a later stage / a human / CI) ----------
    print(f"\nreverify (re-runs the receipt independently): {reverify(a, cwd=str(work))}")

    # --- and if the work later regresses, reverify catches it ----------------
    (work / "widget.py").write_text("def compute():\n    return 0\n")  # broke it
    try:
        reverify(a, cwd=str(work))
    except Exception as e:
        print(f"after a regression, reverify FLAGS it: {type(e).__name__}: "
              f"{str(e).splitlines()[0]}")


if __name__ == "__main__":
    main()
