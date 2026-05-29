"""A narrated demo: watch the mask block the shortcuts in real time.

Run:  PYTHONPATH=. python3 forcing_function/demo.py
"""

from forcing_function.constrained_decode import (
    ForcingDecoder, START, TEXT, SRC, KEY, REL, CLOSE, EOF, RECONCILERS,
)
from forcing_function.models import AdversarialModel


def narrate(plan, title):
    print(f"\n=== {title} ===")
    print("The model WANTS to: state each claim and close it immediately —")
    print("no source, no reconciliation. Watch what the mask permits.\n")
    d = ForcingDecoder()
    model = AdversarialModel(plan)
    step = 0
    while not d.state.done:
        step += 1
        legal = d.legal_types()
        atype, value = model.propose(d.state, legal)
        # show when the model wanted to close but couldn't
        wanted_close = CLOSE not in legal and d.state.cur and d.state.cur.text
        note = ""
        if wanted_close and atype == SRC:
            note = "  <- CLOSE was MASKED (no source yet); forced to add one"
        if wanted_close and atype == REL:
            note = "  <- CLOSE was MASKED (key conflicts); forced to reconcile"
        legal_str = ",".join(sorted(legal))
        val_str = "" if value is None else f" {value!r}"
        print(f"  step {step:>2}: legal={{{legal_str}}}  ->  {atype}{val_str}{note}")
        d.apply(atype, value)

    print("\n  FINAL DOCUMENT (everything that survived the mask):")
    for c in d.state.output:
        rels = "  ".join(f"{rt}->{tgt}" for rt, tgt in c.rels) or "-"
        key = c.key or "-"
        print(f"    [{c.id}] {c.text!r}  src={c.src!r}  key={key}  rels={rels}")


if __name__ == "__main__":
    # 1) An adversary that wants to assert a bare fact with no source.
    narrate(
        [{"text": "caffeine half-life is 5h", "id": "a1"}],
        "Provenance is forced",
    )

    # 2) An adversary that wants to assert a SECOND, conflicting fact on the
    #    same key, and slip it in without admitting the contradiction.
    narrate(
        [
            {"text": "caffeine half-life is 5h", "key": "half-life", "id": "a1"},
            {"text": "caffeine half-life is 3h", "key": "half-life", "id": "a2"},
        ],
        "Reconciliation is forced",
    )

    print("\nNote: the forced source reads 'UNVERIFIED' and the forced edge may")
    print("point at the wrong claim. The mask guarantees the source EXISTS and")
    print("the conflict is ADMITTED — presence and shape, never truth.")
