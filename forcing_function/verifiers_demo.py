"""One ledger, three receipt kinds — and the §13 gain made concrete.

A model in JSON/value-only mode emitted a charge amount of 23734 cents for the
cart below (a real wrong value from the FINDINGS §13 runs; truth is 33681). A
RecomputeVerifier binds that emitted argument to an independent reference
computation and REFUSES it — deterministically, zero model tokens — where a
value-only function-call interface would have charged the customer the wrong sum.

Run: PYTHONPATH=. python3 forcing_function/verifiers_demo.py
"""
from forcing_function.verifiers import Ledger, Recompute, Command, Quote, Unverified, reverify

ITEMS = [(3,1299),(1,4999),(2,750),(5,199),(1,12500),(4,325),(2,1899),(1,649),(3,1250),(2,499)]


def cart_total(items, shipping, coupon):
    return sum(q * p for q, p in items) + shipping - coupon


def main():
    led = Ledger()

    # 1) RECOMPUTE — the §13 gain: a computed function-call argument.
    print("A model emitted total_cents=23734 (JSON/value-only mode).")
    try:
        led.record("charge", Recompute(
            claim="charge the customer 23734 cents",
            fn=cart_total,
            inputs={"items": ITEMS, "shipping": 1295, "coupon": 2000},
            claimed=23734))
        print("  recorded (BAD!)")
    except Unverified as e:
        print(f"  REFUSED: {e}")
    # the correct value binds fine
    r = led.record("charge", Recompute(
        claim="charge the customer 33681 cents", fn=cart_total,
        inputs={"items": ITEMS, "shipping": 1295, "coupon": 2000}, claimed=33681))
    print(f"  correct value recorded: ok={r.ok} expected={r.evidence['expected']}")

    # 2) COMMAND — an execution claim, same ledger.
    led.record("tests", Command("unit tests pass",
                                cmd=["python3", "-c", "assert 2+2==4"]))
    # 3) QUOTE — a factual claim bound to a source, same ledger.
    src = "Device X is approved for adults. The battery lasts 8 hours."
    led.record("fact", Quote("battery lasts 8 hours", src, "battery lasts 8 hours"))

    print("\nLedger (only verified claims got in):")
    for cid, kind, claim in led.summary():
        print(f"  [{kind:9}] {cid}: {claim}")

    # reverify across a handoff (re-supply the live roots for quote/recompute)
    rc = led.receipts[0][1]
    print(f"\nreverify(recompute) = {reverify(rc, fn=cart_total)}")
    print(f"reverify(command)   = {reverify(led.receipts[1][1])}")
    print(f"reverify(quote)     = {reverify(led.receipts[2][1], source=src)}")


if __name__ == "__main__":
    main()
