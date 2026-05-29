"""Agent-pipeline isolation test: temporal trust handoff.

Producer mints claims at T0 (each verified, with a trusted link). Sources then
DRIFT before a later stage consumes them: one source's content changes, one
source's link repoints to an untrusted origin. The consumer must flag the claims
that are no longer safe.

This isolates the scenario where the ledger's mechanical value is supposed to be
real: the consumer is not the producer and cannot re-read everything by hand at
scale. reverify() does it in O(1) per claim, deterministically.

Honest finding (see README): in head-to-head runs a capable model (Opus) given
the same drifted sources flagged the same claims by reasoning. The ledger's edge
is not "catches what the model can't" but "does it deterministically, at zero
model cost, and auditably" — a guarantee, not a judgment call.

Run: PYTHONPATH=. python3 forcing_function/example_pipeline.py
"""
from forcing_function.grounded import SourcePool, GroundedDecoder, reverify, TamperedSource

TRUSTED = {"eur-lex.europa.eu"}


def main():
    s0 = {
        "reg-1": "The additive E-200 is banned in food.",
        "reg-2": "The maximum residue limit is 5 mg/kg.",
        "reg-3": "Labeling in the national language is mandatory.",
        "reg-4": "Import permits are valid for 12 months.",
        "reg-5": "Penalties may reach 50,000 euro.",
    }
    u0 = {k: f"https://eur-lex.europa.eu/{k}" for k in s0}
    gd = GroundedDecoder(SourcePool(s0, uris=u0, trusted_domains=TRUSTED),
                         require_trusted_link=True)
    claims = [gd.cite(cid=k, text=t, src=k, quote=t) for k, t in s0.items()]
    print(f"T0: producer minted {len(claims)} verified claims.")

    # Drift: reg-2 content changes (5 -> 50), reg-4 link repoints off-allowlist.
    s2 = dict(s0, **{"reg-2": "The maximum residue limit is 50 mg/kg."})
    u2 = dict(u0, **{"reg-4": "https://evil-mirror.example/reg-4"})
    pool2 = SourcePool(s2, uris=u2, trusted_domains=TRUSTED)
    print("Drift: reg-2 content changed; reg-4 link repointed to untrusted origin.")
    print("Ground truth unsafe: reg-2, reg-4\n")

    flagged = []
    for c in claims:
        try:
            reverify(pool2, c, require_trusted_link=True)
            print(f"  {c.id}: OK")
        except TamperedSource as e:
            flagged.append(c.id)
            print(f"  {c.id}: FLAGGED -> {e}")
    print("\nflagged:", flagged, "| expected: ['reg-2', 'reg-4']")
    assert flagged == ["reg-2", "reg-4"]
    print("PASS")


if __name__ == "__main__":
    main()
