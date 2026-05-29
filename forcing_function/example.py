"""A runnable example of the citation ledger — the working form of the README.

A compliance question is answered against a fixed source pool. The point of the
example is the accountability property: the model can only record a claim it can
bind to a verbatim quote, so facts the sources do not contain (here: pediatric
approval, maximum continuous operating time, MRI-compatibility) simply cannot be
asserted — they are left unstated rather than fabricated.

Run:
    cd /home/user/awesome-swift && PYTHONPATH=. python3 forcing_function/example.py
"""

from forcing_function.grounded import SourcePool, GroundedDecoder


def build():
    pool = SourcePool({
        "d1": "Device X is approved for use in adults.",
        "d2": "Device X must be sterilized before each use.",
        "d3": "Device X's battery lasts 8 hours on a full charge.",
        "d4": "Device X is manufactured in Germany.",
        "d5": "The recommended storage temperature for Device X is 2-8 degrees Celsius.",
        "d6": "Device X received CE marking in 2021.",
        "d7": "Device X's warranty period is 24 months.",
    })
    gd = GroundedDecoder(pool)

    # Only facts that bind to a verbatim quote can be recorded.
    gd.cite(cid="k1",
            text="Device X is approved for use in adults.",
            src="d1",
            quote="Device X is approved for use in adults.")
    gd.cite(cid="k2",
            text="Device X's battery lasts 8 hours on a full charge.",
            src="d3",
            quote="Device X's battery lasts 8 hours on a full charge.")

    # Pediatric approval, maximum continuous operating time, and MRI-compatibility
    # are NOT in the sources, so there is no quote to bind — they cannot be cited,
    # and the honest answer is "not stated in sources."
    return gd


def main():
    gd = build()
    print("Recorded, source-bound claims:")
    for c in gd.claims:
        print(f"  {c.id} | {c.text} | {c.src} | {c.quote!r}")
    print("\nNot stated in sources (cannot be cited, must not be asserted):")
    print("  - pediatric / children approval")
    print("  - maximum continuous operating time")
    print("  - MRI-compatibility")


if __name__ == "__main__":
    main()
