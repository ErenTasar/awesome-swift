# FINDINGS — what we learned building the Citation Ledger

A standing, falsifiable record of the conclusions reached while taking the AIDF
idea down to its core and stress-testing it. Written to be **questioned**, not to
flatter the project. Every claim below is tied to a reproducible artifact (a
commit, a script, or an eval you can re-run). If a finding is wrong, it should be
wrong *here*, in the open, where the next person can overturn it.

Branch: `claude/citation-ledger-pentest-ab-6DmKC`. Tests: `PYTHONPATH=. pytest
forcing_function/` (25, all green). Code under test: `forcing_function/grounded.py`.

---

## 0. What the thing is (one paragraph)

A small, non-bypassable surface (`GroundedDecoder.cite()`) that records a model's
factual claims only if each binds to a real source id and a verbatim quote, with
conflicting claims forced to carry an explicit reconciling edge, plus an optional
full-context `judge`. `reverify()` re-checks a recorded claim against the
(possibly reloaded) pool. It is the one surviving core of a larger format (AIDF);
the token-mask "decoder", grammar, and demos were deleted once evals showed they
added nothing over the API. **Form is provable; meaning is judged.**

---

## 1. The headline result, stated plainly

Across every axis we tested, **the tool does not make a capable model more
correct, more honest, or better at detection.** On accuracy, content honesty, and
drift detection the model alone was already at ceiling — strong and weak models
alike. Where the tool has any edge it is an *engineering* property (determinism,
zero-model-cost, auditability), not an *intelligence* property. This was the
user's hypothesis from the start ("benefit is expected to be marginal because
Claude is strong"); it survived repeated, deliberately adversarial testing.

This is a **negative result reported as a result.** It is the deliverable.

---

## 2. The evidence, axis by axis

| axis | tool's benefit | how we know | artifact |
|------|----------------|-------------|----------|
| Accuracy | **0** | n=8 A/B (Opus/Sonnet/Haiku), grounded vs free-form-asked-to-cite; identical hard-case accuracy | git history: `eval_treatment*`, `eval_opus_treatment` |
| Content honesty | **0** | accountability A/B; both control models surfaced the corrected figure, neither invented a fact; weak ≈ strong | README "Accountability A/B"; commit `f471c7f` |
| Drift detection (pipeline) | **0** | temporal-handoff test; Opus & Haiku, given drifted sources, flagged the same claims incl. link-repoint and a subtle "per day" edit | `example_pipeline.py`; commit `b5057f9` |
| Determinism / cost / auditability | **marginal, >0** | `reverify()` is O(1)/claim, 0 tokens, deterministic, leaves a checkable record; a model call is none of these | `example_pipeline.py`, README pipeline table |
| Structural-defect rejection | **narrow, real, partly by-construction** | accountability A/B: control shipped a null-source claim (Haiku) and an unlinked conflict that *looked* reconciled (Opus); treatment refused both | README A/B table |

Caveats kept honest: A/B cells are n=1; the control arm was *given* structured
(id, quote) output it would not have in true free form and still leaked one defect
per cell. So the structural-defect finding is "this class of defect can ship and
the mechanism refuses it," not a calibrated rate.

---

## 3. The pentest (the tool's own value, demonstrated on itself)

A red-team found two **real mechanical bugs**, both fixed with regression tests
(commit `edf8a35`):

- **V1:** a conflicting claim (reused `key`) was accepted with a reconciling edge
  pointing at an *unrelated* claim — so two conflicting facts could be recorded
  *unlinked*, silently violating the core reconciliation guarantee. Fix: the edge
  must target a claim sharing that key. (Independently reproduced on the pre-fix
  code: the old build accepted it; the new build refuses it.)
- **V3:** `reverify()` was fail-*open* on a blank quote while `cite()` was
  fail-closed. Fix: `reverify()` fails closed on a missing/blank quote.

Everything else held: self/cyclic edges refused; the trusted-link URL battery
(userinfo `@`, trailing dot, subdomain, punycode, scheme-relative, tab/newline,
backslash) is uniformly fail-closed; extractive `.strip()` is whitespace-only.

Meta-finding (the sharpest single piece of evidence): in one Opus run an agent
wrote an eval script against a **non-existent API** (`gd.finalized()`, `c.cid`)
and confidently reported **"runs cleanly."** It had never run; only manual
execution caught it. A strong model is not *less* accurate — it is *more
convincingly wrong*, and the cost of catching that rises. That is the entire case
for an external, mechanical check, demonstrated by accident on ourselves.

---

## 4. The structural theorem (why no new niche rescued it)

We chased three "model-impossible" axes hoping to find value only the tool could
deliver. Each collapsed onto the **same** structure:

| candidate axis | where the real value actually sits | who holds it (not us) |
|----------------|-------------------------------------|-----------------------|
| trusted provenance | the trusted-domain allowlist | whoever curates the allowlist |
| non-repudiation (prove the past) | external timestamp / transparency log / blockchain anchor (RFC 3161, OpenTimestamps, Certificate Transparency) | a third-party authority |
| output authenticity ("the AI really said this") | the provider's signing key / watermark (C2PA / Content Credentials, SynthID) | the model provider |

**Generalization:** every genuinely *model-impossible* value bottoms out at a
**trust root**, and that root is always either the model provider or an external
authority. An API-level, key-less, logit-less third-party library holds none of
these roots. Therefore, from our position, there is **no model-impossible value to
build** — not for lack of effort, but structurally. We hit the same wall three
times; the third time it stopped being a coincidence and became the finding.

What's left for a third party is the *verifier* role on top of someone else's
root (e.g. check a provider signature, check a TSA token) — which is plumbing
around an external guarantee, not a guarantee we create.

---

## 5. The one honest sentence of value

> The Citation Ledger does not make a strong model smarter, more honest, or more
> vigilant — measured, repeatedly, against Opus/Sonnet/Haiku it is model-neutral.
> Its only real contribution is **deterministic, zero-cost, auditable rejection of
> structurally broken citations and conflicts** a reader would wave through —
> useful precisely where the producer is not the reader and the check must be
> cheap, repeatable, and itself verifiable (high-volume or high-stakes pipelines).
> Everything beyond that depends on a trust root we do not hold.

---

## 6. How to falsify these findings (open questions for the next person)

- **Accuracy=0 is n-limited.** Run larger n, harder corpora, or a *weak/uncareful*
  generator (not Opus). If grounded mode ever beats free-form on accuracy at scale,
  Finding §1 is wrong.
- **Structural-defect rate.** We showed the class can ship; we did not measure how
  often. Quantify the leak rate of null-source / unlinked-conflict defects in true
  free-form output (not the structured-handicapped control we used).
- **The theorem (§4) is the load-bearing claim.** To break it, name a value that is
  (a) model-impossible alone, (b) genuinely useful, and (c) deliverable by an
  API-level third party *without* leaning on a provider key or external authority.
  We could not. If one exists, that is the project.
- **Verifier-role value.** The one role left to a third party is verifying someone
  else's root. Is there a real, non-trivial product there, or is it just plumbing?
