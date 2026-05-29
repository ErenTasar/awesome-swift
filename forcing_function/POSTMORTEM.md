# POSTMORTEM — what this project got wrong, and the general lessons

A closing, deliberately unflattering account of where the effort went and where it
was wasted. The point is not to rescue the project but to extract lessons general
enough to apply to the *next* one. Every lesson is tied to a concrete misstep from
this work so it can't be hand-waved. Read alongside `FINDINGS.md` (§0–§17), which
records the results; this records the *mistakes*.

---

## The honest verdict

The project never found a defensible, non-marginal value. Every promising avenue —
the citation format, the execution ledger, the generalised receipt, the
"confidence false-positive" finding — survived first contact with enthusiasm and
died on independent inspection. The user's opening hypothesis ("the benefit will be
marginal because the model is strong") was correct, was confirmed from many angles,
and we kept spending effort *re-confirming* it under new disguises instead of
accepting it. That re-confirmation is the bulk of the wasted work.

---

## Inventory of wasted effort (what we built that paid ~nothing)

1. **AIDF: token-mask "decoder", grammar, demos.** Built, then deleted once evals
   showed they added nothing over a plain API call. Pure sunk cost.
2. **Citation Ledger (`grounded.py`).** Model-neutral on accuracy, honesty, and
   drift (Opus/Sonnet/Haiku). Only residue: a marginal engineering property
   (deterministic, zero-token, auditable rejection). Months-of-idea, near-zero value.
3. **The §4 "model-impossible value" hunt.** Three separate niche searches, each
   collapsing onto "you need a trust root you don't hold." Valuable as a *negative*
   theorem, but reached by repeatedly hitting the same wall.
4. **Execution Ledger (`verified.py`) + generalised receipt (`verifiers.py`,
   `tool_guard.py`, `fill()`).** A real, tested mechanism — and still marginal: in a
   world where the agent can run code, an external recompute/command receipt mostly
   re-does what the model already does. Built well, needed little.
5. **The "confidence false-positive" finding (§12–§17).** The one result that felt
   like a real, publishable phenomenon — *capable model + parse-only output channel
   → confident-wrong*. It reproduced in our subagent harness across four cognitive
   modes. Then an independent test on real models/interfaces **did not reproduce
   it**: modern models reason internally regardless of a "no working" instruction,
   so the prompt-level channel restriction we relied on doesn't bind. The effect is
   real but lives in a narrow corner (true API JSON-mode + a non-reasoning model + a
   serial-dependent task), not in the wild. We nearly promoted a rigging artifact to
   a headline.

---

## The general lessons (abstracted)

### 1. Start from a problem, not from a mechanism.
This project began with a *solution* (a forcing function / ledger / receipt) and
spent its life hunting for a value to attach to it. Every "use case" therefore came
out forced. **A mechanism in search of a problem will always find a marginal one.**
Begin from a pain someone actually has; derive the mechanism from it.

### 2. Measure a tool against what the model already does, not against zero.
The relevant baseline is never "nothing" — it is "the capable model, unaided." A
tool that does what a strong model already does well is marginal by construction.
**A tool earns its keep only where the model structurally *cannot* reach** — real
external state, persistence across time, trust transfer between parties, a
computation the model literally can't perform. Those niches are narrow and are about
*access, cost, and trust — not intelligence.* Everything we built that targeted
"make the model more correct" returned zero, exactly as that rule predicts.

### 3. An effect produced by a rigged condition is not a finding until it survives the realistic one.
We isolated the channel effect by *artificially* removing the model's reasoning
channel, then treated the isolation as the phenomenon. The independent, realistic
test killed it. **Ecological validity is not a footnote you add later; it is the
gate.** Reproduce the effect in the most realistic available setting *before*
claiming it generalises. (We even learned this once in §11 — and fell for it again.)

### 4. The confound you note in passing may be the real result.
In §17 we flagged "the model can think before emitting the JSON" as a *confound*.
In reality that was the dominant truth — models reason anyway, which is *why* the
finding doesn't generalise. **When a confound keeps reappearing, stop treating it as
noise and ask whether it is the actual signal.**

### 5. Accept a confirmed negative early; stop re-confirming it in disguise.
The marginal-value hypothesis was supported by the second or third experiment.
Instead of concluding, we pivoted — new niche, new ledger, new "axis" — each
ending at the same place. **Repeated confirmation from independent angles is a
stop signal, not a prompt for another pivot.** The cost of a project is often the
experiments you ran *after* you already knew the answer.

### 6. The strongest verification comes from a channel you don't control.
Our own runs and subagents "confirmed" the finding; the user's independent terminal
test, on models and interfaces we didn't choose, overturned it. **Self-run
validation is the weakest kind.** Seek the cheapest independent check (a different
model, a different harness, a different person) early — it is worth more than ten
in-house repetitions. (This is the same lesson as the project's origin artifact —
an agent that said "runs cleanly" without running — and we still under-applied it.)

### 7. Name the value honestly; don't dress engineering convenience as an intelligence gain.
Determinism, zero-token cost, and auditability were real — but they are *engineering
conveniences*, not a model getting smarter. We repeatedly reached for the second
framing because it sounds bigger. **Categorise a benefit truthfully (convenience vs.
capability vs. trust), and a marginal one will stop masquerading as a breakthrough.**

---

## One-sentence takeaway

> We built mechanisms looking for value against a baseline (a strong model) that
> already had it, kept re-confirming a negative we'd been told at the start, and
> almost shipped a finding that only existed because we'd rigged the test — the
> general fix for all of it is: **start from a real problem, baseline against the
> unaided model, and let an independent channel try to kill your result before you
> believe it.**
