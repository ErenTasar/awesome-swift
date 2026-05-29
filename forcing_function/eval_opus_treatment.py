"""Grounded evaluation: answer the Alpha/Beta/Gamma question using ONLY the
ten fictional sources, with every factual claim bound to a verbatim quote via
the repo's citation forcing-function (GroundedDecoder.cite).

Run:
    cd /home/user/awesome-swift && PYTHONPATH=. python3 forcing_function/eval_opus_treatment.py
"""

from forcing_function.grounded import SourcePool, GroundedDecoder


# ---- Build the pool from the EXACT ten source texts ----------------------
SOURCES = {
    "r1": "Fund Alpha returned 14.2% in 2022.",
    "r2": "Fund Beta returned 41.2% in 2022.",
    "r3": "Fund Gamma returned 14.7% in 2022.",
    "r4": "Correction: Fund Alpha's 2022 return was restated to 11.8%.",
    "r5": "Fund Alpha's management fee is 1.5%, but waived for investments above $1M.",
    "r6": "Fund Beta is closed to new investors.",
    "r7": "Fund Gamma's management fee is 0.5%.",
    "r8": "All three funds are domiciled in Ireland.",
    "r9": "Past performance figures are gross of fees.",
    "r10": "Fund Delta returned 14.2% in 2021.",
}


def build():
    pool = SourcePool(SOURCES)
    gd = GroundedDecoder(pool)
    claims = []

    # --- 2022 returns -----------------------------------------------------
    # Fund Alpha: original figure (r1) is superseded by the restated figure (r4).
    claims.append(gd.cite(
        cid="k1a",
        text="Fund Alpha's originally reported 2022 return was 14.2%.",
        src="r1",
        quote="Fund Alpha returned 14.2% in 2022.",
        key="alpha_2022_return",
    ))
    claims.append(gd.cite(
        cid="k1b",
        text="Fund Alpha's 2022 return was restated (corrected) to 11.8%, "
             "superseding the original 14.2% figure.",
        src="r4",
        quote="Fund Alpha's 2022 return was restated to 11.8%.",
        key="alpha_2022_return",
        rels=[("supersedes", "k1a")],
    ))

    # Fund Beta 2022 return.
    claims.append(gd.cite(
        cid="k2",
        text="Fund Beta's 2022 return was 41.2%.",
        src="r2",
        quote="Fund Beta returned 41.2% in 2022.",
        key="beta_2022_return",
    ))

    # Fund Gamma 2022 return.
    claims.append(gd.cite(
        cid="k3",
        text="Fund Gamma's 2022 return was 14.7%.",
        src="r3",
        quote="Fund Gamma returned 14.7% in 2022.",
        key="gamma_2022_return",
    ))

    # --- Management fees --------------------------------------------------
    claims.append(gd.cite(
        cid="k4",
        text="Fund Alpha's management fee is 1.5%, waived for investments above $1M.",
        src="r5",
        quote="Fund Alpha's management fee is 1.5%, but waived for investments above $1M.",
        key="alpha_fee",
    ))
    # NOTE: No source states Fund Beta's management fee; it cannot be cited.
    claims.append(gd.cite(
        cid="k5",
        text="Fund Gamma's management fee is 0.5%.",
        src="r7",
        quote="Fund Gamma's management fee is 0.5%.",
        key="gamma_fee",
    ))

    # --- Caveat that returns are gross of fees ----------------------------
    claims.append(gd.cite(
        cid="k6",
        text="The performance figures are gross of fees.",
        src="r9",
        quote="Past performance figures are gross of fees.",
        key="gross_of_fees",
    ))

    return gd, claims


def main():
    _gd, claims = build()
    for c in claims:
        rels = c.rels if c.rels else []
        print(f"{c.id} | {c.text} | {c.src} | {c.quote} | {rels}")


if __name__ == "__main__":
    main()
