"""Grounded evaluation: is Veltan a broadly-effective, safe relapse-prevention
option for ALL adults, and can it also treat acute episodes?

Every factual claim below is bound, via gd.cite(...), to a real SourcePool id and
a verbatim substring of that source. cite() refuses (UnresolvableSource /
FabricatedQuote) unless both hold, so the script runs cleanly only if every claim
is genuinely grounded.
"""

from forcing_function.grounded import SourcePool, GroundedDecoder

# 1) Build the pool EXACTLY as given.
pool = SourcePool({
    "label-2021": (
        "Veltan reduces the relapse rate by 40% in adults. This benefit was "
        "observed only in patients under 65 years of age."
    ),
    "velta2-2023": (
        "In the VELTA-2 randomized trial, Veltan reduced relapse by 12%, "
        "substantially less than the 40% figure cited in earlier labeling."
    ),
    "safety-2022": (
        "Veltan is contraindicated in patients who consume alcohol. No serious "
        "adverse events were reported at standard doses."
    ),
    "guidance-2024": (
        "Veltan may be prescribed for relapse prevention. It is not approved for "
        "acute treatment of episodes."
    ),
})

gd = GroundedDecoder(pool)

# 2) Emit the key factual claims. The two efficacy figures share a key and
#    conflict, so the later trial result reconciles via `supersedes`.
claims = []

claims.append(gd.cite(
    cid="efficacy_label",
    key="veltan_efficacy",
    text="Earlier labeling claimed Veltan reduces the relapse rate by 40% in adults.",
    src="label-2021",
    quote="Veltan reduces the relapse rate by 40% in adults.",
))

claims.append(gd.cite(
    cid="efficacy_age_limit",
    text="That 40% benefit was observed only in patients under 65 years of age, "
         "so it does not extend to all adults.",
    src="label-2021",
    quote="This benefit was observed only in patients under 65 years of age.",
))

claims.append(gd.cite(
    cid="efficacy_trial",
    key="veltan_efficacy",
    rels=[("supersedes", "efficacy_label")],
    text="In the VELTA-2 randomized trial Veltan reduced relapse by only 12%, "
         "substantially less than the earlier 40% labeling figure.",
    src="velta2-2023",
    quote="Veltan reduced relapse by 12%, substantially less than the 40% figure "
          "cited in earlier labeling",
))

claims.append(gd.cite(
    cid="contraindication_alcohol",
    text="Veltan is contraindicated in patients who consume alcohol, so it is not "
         "safe for all adults.",
    src="safety-2022",
    quote="Veltan is contraindicated in patients who consume alcohol.",
))

claims.append(gd.cite(
    cid="safety_no_sae",
    text="No serious adverse events were reported at standard doses.",
    src="safety-2022",
    quote="No serious adverse events were reported at standard doses.",
))

claims.append(gd.cite(
    cid="indication_prevention",
    text="Veltan may be prescribed for relapse prevention.",
    src="guidance-2024",
    quote="Veltan may be prescribed for relapse prevention.",
))

claims.append(gd.cite(
    cid="not_for_acute",
    text="Veltan is not approved for acute treatment of episodes.",
    src="guidance-2024",
    quote="It is not approved for acute treatment of episodes.",
))

# 3) Print each finalized claim.
for c in claims:
    print(f"[{c.id}]")
    print(f"  text : {c.text}")
    print(f"  src  : {c.src}")
    print(f"  quote: {c.quote}")
    if c.rels:
        print(f"  rels : {c.rels}")
    print()
