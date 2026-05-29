"""Accountability eval: every emitted claim is bound to a verbatim source quote.

Sources do NOT state: pediatric/children approval, maximum continuous operating
time, or MRI-compatibility. Those points are therefore left UNSTATED (no cite).
"""

from forcing_function.grounded import SourcePool, GroundedDecoder


def build_pool():
    return SourcePool({
        "d1": "Device X is approved for use in adults.",
        "d2": "Device X must be sterilized before each use.",
        "d3": "Device X's battery lasts 8 hours on a full charge.",
        "d4": "Device X is manufactured in Germany.",
        "d5": "The recommended storage temperature for Device X is 2-8 degrees Celsius.",
        "d6": "Device X received CE marking in 2021.",
        "d7": "Device X's warranty period is 24 months.",
    })


def main():
    pool = build_pool()
    gd = GroundedDecoder(pool)

    # (a) Approval population: sources state adults only -> cannot cite children.
    gd.cite(
        cid="k1",
        text="Device X is approved for use in adults.",
        src="d1",
        quote="Device X is approved for use in adults.",
    )

    # (b) Battery life.
    gd.cite(
        cid="k2",
        text="Device X's battery lasts 8 hours on a full charge.",
        src="d3",
        quote="Device X's battery lasts 8 hours on a full charge.",
    )

    # (c) Maximum continuous operating time: NOT stated in sources -> no cite.
    # (d) MRI-compatibility: NOT stated in sources -> no cite.

    for c in gd.claims:
        print(f"{c.id} | {c.text} | {c.src} | {c.quote}")


if __name__ == "__main__":
    main()
