from forcing_function.grounded import SourcePool, GroundedDecoder

pool = SourcePool({
    "s1": "Refunds are available for all customers.",
    "s2": "Refund eligibility ends 30 days after purchase.",
    "s3": "The new model is faster than the previous one in every benchmark.",
    "s4": "All benchmarks were run only on the vendor's own hardware.",
    "s5": "Smoking is permitted in the lounge.",
    "s6": "From January, the lounge smoking area will be closed permanently.",
})

gd = GroundedDecoder(pool)

gd.cite(cid="b1", text="All customers qualify for refunds.", src="s1", quote="Refunds are available for all customers.")
gd.cite(cid="b2", text="Refund window closes 30 days after purchase.", src="s2", quote="Refund eligibility ends 30 days after purchase.")
gd.cite(cid="b3", text="New model beats the previous one in every benchmark.", src="s3", quote="The new model is faster than the previous one in every benchmark.")
gd.cite(cid="b4", text="Benchmarks were run exclusively on the vendor's own hardware.", src="s4", quote="All benchmarks were run only on the vendor's own hardware.")
gd.cite(cid="b5", text="Smoking is currently permitted in the lounge.", src="s5", quote="Smoking is permitted in the lounge.")
gd.cite(cid="b6", text="Lounge smoking area closes permanently from January.", src="s6", quote="From January, the lounge smoking area will be closed permanently.")

for c in gd.claims:
    print(f"{c.id} | {c.text} | {c.src} | {c.quote}")
