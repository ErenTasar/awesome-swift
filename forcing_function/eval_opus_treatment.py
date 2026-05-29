"""Grounded evaluation: 2022 returns and management fees for Funds Alpha, Beta, Gamma.

Builds the SourcePool from the EXACT ten source texts, emits every claim needed to
answer the question via gd.cite(...), and prints each finalized claim as:
    cid | text | src | quote | rels
"""

from forcing_function.grounded import SourcePool, GroundedDecoder


def build_pool() -> SourcePool:
    return SourcePool(
        {
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
    )


def emit_claims(gd: GroundedDecoder) -> None:
    # --- 2022 returns ---
    # Fund Alpha: original figure, then superseded by the correction.
    gd.cite(
        cid="alpha_return_orig",
        text="Fund Alpha's originally reported 2022 return was 14.2%.",
        src="r1",
        quote="Fund Alpha returned 14.2% in 2022.",
        key="alpha_2022_return",
    )
    gd.cite(
        cid="alpha_return_restated",
        text="Fund Alpha's 2022 return was restated to 11.8% (this supersedes the original 14.2% figure).",
        src="r4",
        quote="Fund Alpha's 2022 return was restated to 11.8%.",
        key="alpha_2022_return",
        rels=[("supersedes", "alpha_return_orig")],
    )

    # Fund Beta 2022 return.
    gd.cite(
        cid="beta_return",
        text="Fund Beta returned 41.2% in 2022.",
        src="r2",
        quote="Fund Beta returned 41.2% in 2022.",
        key="beta_2022_return",
    )

    # Fund Gamma 2022 return.
    gd.cite(
        cid="gamma_return",
        text="Fund Gamma returned 14.7% in 2022.",
        src="r3",
        quote="Fund Gamma returned 14.7% in 2022.",
        key="gamma_2022_return",
    )

    # --- Management fees ---
    gd.cite(
        cid="alpha_fee",
        text="Fund Alpha's management fee is 1.5%, but it is waived for investments above $1M.",
        src="r5",
        quote="Fund Alpha's management fee is 1.5%, but waived for investments above $1M.",
        key="alpha_fee",
    )
    # Fund Beta: no management fee is stated in any source, so none can be cited.
    gd.cite(
        cid="gamma_fee",
        text="Fund Gamma's management fee is 0.5%.",
        src="r7",
        quote="Fund Gamma's management fee is 0.5%.",
        key="gamma_fee",
    )

    # --- Context needed to interpret performance correctly ---
    gd.cite(
        cid="gross_of_fees",
        text="The reported past performance figures are gross of fees.",
        src="r9",
        quote="Past performance figures are gross of fees.",
        key="performance_basis",
    )


def main() -> None:
    pool = build_pool()
    gd = GroundedDecoder(pool)
    emit_claims(gd)

    for c in gd.finalized():
        rels_str = ", ".join(f"({r[0]},{r[1]})" for r in c.rels) if c.rels else "-"
        print(f"{c.cid} | {c.text} | {c.src} | {c.quote} | {rels_str}")


if __name__ == "__main__":
    main()
