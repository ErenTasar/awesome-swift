"""The §13 fix, end-to-end: a value-only tool call whose computed field is guarded.

A function-calling agent emits a `charge` call as JSON arguments — including
`total_cents`, a derived field it had no room to actually compute (the §13 regime).
GuardedTool recomputes it from the emitted line items and REFUSES the wrong call,
handing back a correction the agent can re-emit with. Round two — the corrected
value — passes and is recorded to a ledger. Deterministic, zero model tokens.

Run: PYTHONPATH=. python3 forcing_function/tool_guard_demo.py
"""
from forcing_function.tool_guard import GuardedTool, Derived
from forcing_function.verifiers import Ledger, Unverified


def cart_total(items, shipping, coupon):
    return sum(q * p for q, p in items) + shipping - coupon


CART = {"items": [[3, 1299], [1, 4999], [2, 750], [5, 199], [1, 12500],
                  [4, 325], [2, 1899], [1, 649], [3, 1250], [2, 499]],
        "shipping": 1295, "coupon": 2000}

CHARGE = GuardedTool("charge", computed={
    "total_cents": Derived(cart_total, ["items", "shipping", "coupon"])})


def agent_emit(corrected=False):
    """Stand-in for the model's structured emit. Round 1 is the real §13
    confidently-wrong value (23734); round 2 is the agent's re-emit."""
    return {**CART, "total_cents": 33681 if corrected else 23734}


def main():
    led = Ledger()

    print("Round 1: agent emits the charge call (value-only channel).")
    res = CHARGE.validate(agent_emit(), ledger=led, id_prefix="charge.")
    print(f"  emitted total_cents = {res.args['total_cents']}")
    print(f"  call allowed? {res.ok}")
    print("  --- correction handed back to the agent ---")
    print("  " + res.retry_prompt().replace("\n", "\n  "))

    print("\nRound 2: agent re-emits with the corrected value.")
    res = CHARGE.validate(agent_emit(corrected=True), ledger=led, id_prefix="charge.")
    print(f"  emitted total_cents = {res.args['total_cents']}")
    print(f"  call allowed? {res.ok}")

    print("\nLedger (only the verified call got in):")
    for cid, kind, claim in led.summary():
        print(f"  [{kind}] {cid}: {claim}")

    # enforce() is the fail-closed path for a call site that must not proceed
    print("\nenforce() on the wrong value raises (fail-closed):")
    try:
        CHARGE.enforce(agent_emit())
    except Unverified:
        print("  Unverified raised — the wrong charge never executed.")


if __name__ == "__main__":
    main()
