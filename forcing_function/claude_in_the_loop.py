"""Claude (or any real model) in the forcing loop.

The Anthropic API exposes no logits, so a model cannot be masked at the *token*
level. It can be connected at the *action* level: the model calls `emit()` with
what it wants to assert, and the forcing function refuses — raises — until the
claim carries a non-empty source and, on a conflict, an explicit reconciling
edge. The model physically cannot finalize a claim without them.

The loop below is what an agent does: try to assert, get refused, supply the
missing piece, succeed. Run:

    PYTHONPATH=. python3 forcing_function/claude_in_the_loop.py
"""

from forcing_function.constrained_decode import (
    ForcingDecoder, NeedsProvenance, NeedsReconciliation)


def assert_claim(d, **claim):
    """One agent turn: try to assert; if refused, report what the mask demands."""
    try:
        c = d.emit(**claim)
        print(f"  ok    [{c.id}] {c.text!r}  src={c.src!r}"
              + (f"  rels={c.rels}" if c.rels else ""))
        return True
    except (NeedsProvenance, NeedsReconciliation) as e:
        print(f"  REFUSED {claim.get('cid')!r}: {e}")
        return False


if __name__ == "__main__":
    d = ForcingDecoder()

    print("Claim 1 — I (the model) try to just state the fact, no source:")
    assert_claim(d, cid="c1", text="Australia's capital is Canberra",
                 key="au-capital")
    print("...refused, so I attach the source I actually have:")
    assert_claim(d, cid="c1", text="Australia's capital is Canberra",
                 key="au-capital", src="worldatlas-2024")

    print("\nClaim 2 — the common misconception; I try to slip it in silently:")
    assert_claim(d, cid="c2", text="Australia's capital is Sydney",
                 key="au-capital", src="popular-belief")
    print("...refused (it conflicts with c1), so I admit the contradiction:")
    assert_claim(d, cid="c2", text="Australia's capital is Sydney",
                 key="au-capital", src="popular-belief",
                 rels=[("contradicts", "c1")])

    print("\nDocument the forcing function let me produce:")
    for c in d.state.output:
        rels = ", ".join(f"{rt}->{tgt}" for rt, tgt in c.rels) or "-"
        print(f"  [{c.id}] {c.text!r}  src={c.src!r}  rels={rels}")
