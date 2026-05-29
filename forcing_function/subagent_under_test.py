"""Stress-test of the ForcingDecoder guardrail.

Run with:
    cd /home/user/awesome-swift && PYTHONPATH=. python3 forcing_function/subagent_under_test.py
"""

from forcing_function.constrained_decode import (
    ForcingDecoder,
    NeedsProvenance,
    NeedsReconciliation,
)


def main():
    d = ForcingDecoder()

    # ------------------------------------------------------------------
    # Claim 1: Pluto was the ninth planet.
    # First attempt: lazy model, no src.
    # ------------------------------------------------------------------
    print("=== Claim 1: pluto-ninth-planet ===")
    try:
        d.emit(
            cid="pluto-ninth-planet",
            text="Pluto was classified as the ninth planet of the Solar System.",
            key="pluto-status",
        )
        print("  finalized on first try (no refusal!)")
    except NeedsProvenance as e:
        print(f"  REFUSED (NeedsProvenance): {e}")
    except NeedsReconciliation as e:
        print(f"  REFUSED (NeedsReconciliation): {e}")

    # Retry with a src. I was given no source, so this is a placeholder
    # (see report section C) -- a plausible-looking citation, NOT verified.
    c1 = d.emit(
        cid="pluto-ninth-planet",
        text="Pluto was classified as the ninth planet of the Solar System.",
        src="general astronomical knowledge (pre-2006 planetary classification)",
        key="pluto-status",
    )
    print(f"  finalized after retry: id={c1.id!r}")

    # ------------------------------------------------------------------
    # Claim 2: Pluto is a dwarf planet. Conflicts with claim 1 (same key).
    # First attempt: lazy model, no src AND no reconciling edge.
    # ------------------------------------------------------------------
    print("\n=== Claim 2: pluto-dwarf-planet (conflicts via key 'pluto-status') ===")
    try:
        d.emit(
            cid="pluto-dwarf-planet",
            text="Pluto is classified as a dwarf planet.",
            key="pluto-status",
        )
        print("  finalized on first try (no refusal!)")
    except NeedsProvenance as e:
        print(f"  REFUSED (NeedsProvenance): {e}")
    except NeedsReconciliation as e:
        print(f"  REFUSED (NeedsReconciliation): {e}")

    # Second attempt: add a src but STILL no reconciling edge -- to see
    # which guard fires next.
    try:
        d.emit(
            cid="pluto-dwarf-planet",
            text="Pluto is classified as a dwarf planet.",
            src="general astronomical knowledge (IAU 2006 reclassification)",
            key="pluto-status",
        )
        print("  finalized with src but no edge (no refusal!)")
    except NeedsProvenance as e:
        print(f"  REFUSED (NeedsProvenance): {e}")
    except NeedsReconciliation as e:
        print(f"  REFUSED (NeedsReconciliation): {e}")

    # Final attempt: supply src AND a reconciling edge that supersedes claim 1.
    c2 = d.emit(
        cid="pluto-dwarf-planet",
        text="Pluto is classified as a dwarf planet.",
        src="general astronomical knowledge (IAU 2006 reclassification)",
        key="pluto-status",
        rels=[("supersedes", "pluto-ninth-planet")],
    )
    print(f"  finalized after retry: id={c2.id!r} rels={c2.rels}")

    # ------------------------------------------------------------------
    # Claim 3: Water boils at 100 C. No conflict, so no key needed.
    # First attempt: lazy model, no src.
    # ------------------------------------------------------------------
    print("\n=== Claim 3: water-boiling-point ===")
    try:
        d.emit(
            cid="water-boiling-point",
            text="Water boils at 100 degrees Celsius.",
        )
        print("  finalized on first try (no refusal!)")
    except NeedsProvenance as e:
        print(f"  REFUSED (NeedsProvenance): {e}")
    except NeedsReconciliation as e:
        print(f"  REFUSED (NeedsReconciliation): {e}")

    c3 = d.emit(
        cid="water-boiling-point",
        text="Water boils at 100 degrees Celsius.",
        src="general physics knowledge (at standard atmospheric pressure)",
    )
    print(f"  finalized after retry: id={c3.id!r}")

    # ------------------------------------------------------------------
    # Final document
    # ------------------------------------------------------------------
    print("\n=== FINAL DOCUMENT ===")
    for c in d.state.output:
        print(f"  id:   {c.id}")
        print(f"  text: {c.text}")
        print(f"  src:  {c.src}")
        print(f"  key:  {c.key}")
        print(f"  rels: {c.rels}")
        print()


if __name__ == "__main__":
    main()
