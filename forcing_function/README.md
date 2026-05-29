# Citation Ledger

The one idea worth keeping from the AIDF experiment, trimmed to what actually
earns its place as an **accountability** layer for models reached through an API
(no logit access).

## What this is

A small, non-bypassable surface for recording **cited claims**. A model proposes
a claim; the ledger records it only if the claim is bound to a real source and a
verbatim quote, conflicting claims are explicitly reconciled, and (optionally) a
judge with full context accepts it. An ungrounded or unreconciled claim is never
recorded — there is no other path to record one.

```python
from forcing_function.grounded import SourcePool, GroundedDecoder

pool = SourcePool({"label-2021": "Veltan reduces the relapse rate by 40% in adults. ..."})
gd = GroundedDecoder(pool)
gd.cite(cid="k1",
        text="Veltan reduces relapse by 40%.",
        src="label-2021",
        quote="Veltan reduces the relapse rate by 40% in adults.")   # must be verbatim
```

`cite()` raises unless `src` is a real pool id and `quote` is an exact substring
of that source; conflicting claims (shared `key`) raise until given a reconciling
edge.

## What it is for (and what it is not)

Across n=8 A/B runs on three models (Opus / Sonnet / Haiku), grounded mode
produced **no accuracy gain** over a free-form answer that was already asked to
cite. Strong or weak, the model got the hard cases right either way. So this is
**not an accuracy aid** — it does not make a capable model smarter.

What it *is*: an **accountability** layer — it makes a model's output verifiable
by someone who was not in the room. The sharpest evidence arrived by accident: in
one Opus run an agent wrote an eval script against a *non-existent* API
(`gd.finalized()`, `c.cid`) and confidently reported "runs cleanly." It had never
run; a human caught it only by executing it. That is the thesis in one event — a
strong model is not *less* accurate, it is *more convincingly wrong*, and the cost
of catching that rises. `cite()` would have refused an unsourced step; `reverify()`
checks an "it works" claim independently, automatically, for free.

**Cost is not the objection.** `cite()` is a substring + hash check —
microseconds, zero model tokens; the marginal cost over a normal answer is a few
tokens of structure. The real limit is **scope**: it earns its place where the
producer is not the reader — legal memos, clinical summaries, compliance reports,
agent pipelines where one step must trust another's output. For low-stakes
single-user chat it is overhead.

### Accountability A/B (n=1 per cell, fictional 5-question scenario)

A second A/B, on the accountability axis this time. Two models (Opus, Haiku)
answered five questions about a *fictional* drug under two contracts: **control**
(free report, asked to cite, "answer every question") and **treatment** (the
ledger — a fact must bind to a verbatim quote or be left "not stated"; conflicts
need a reconciling edge). Every proposed claim was then graded mechanically
through `grounded.py`; the model's own "it works" was never trusted — each output
was re-run by hand, per the accident above.

| arm | shipped defects (reach reader) | conflict recorded as edge | abstained on the 2 absent-fact traps | post-hoc tamper detectable |
|-----|----|----|----|----|
| control × Opus  | 1 — a `supersedes` edge pointing at a not-yet-recorded claim, so the conflict was never actually linked | no  | no — attached a real but tangential quote | n/a (free prose has no `src_hash`) |
| control × Haiku | 1 — a claim with a `null` source | yes | no — same over-citation | n/a |
| treatment × Opus  | 0 | yes | yes | 4/4 |
| treatment × Haiku | 0 | yes | yes | 4/4 |

Read honestly:

- **No content/honesty gap, and strength bought nothing.** Both control models
  surfaced the corrected figure in prose and neither invented a cure rate; weak ≈
  strong on every cell. The effect, where there is one, is the mechanism's, not
  the model's — the same conclusion the accuracy run reached.
- **What the ledger mechanically caught** that a reader would likely wave through:
  a claim with no resolvable source (Haiku), and an edge that *looked* reconciled
  in prose but did not resolve, leaving two conflicting figures stored unlinked
  (Opus). Both shipped in control; both were refused in treatment.
- **What was behavioral, not mechanical.** On the absent-fact traps the control
  models attached a verbatim-but-tangential quote — which *passes* `cite()` (the
  quote is real). The treatment models abstained because the contract told them
  to, not because the mechanism forced it. Semantic over-citation is the judge's
  job, not the mechanism's — exactly the documented residue.
- **What is structural** (and must not be oversold): treatment auditability 1.00
  and tamper-detection 4/4 hold partly by construction — `cite()` refuses what it
  cannot verify, and records an `src_hash` free prose never has. The honest claim
  is not "the tool made the model better" but "the tool makes provenance checkable
  by someone who was not in the room, and refuses the structurally broken
  citations a reader would miss."

Caveats: n=1 per cell; the control arm was *given* structured (id, quote) output
it would not have in true free form, and still shipped a defect in each cell.

### Agent-pipeline isolation (temporal trust handoff)

The cleanest case for the ledger: a *consumer* stage must trust a *producer*
stage's claims, but sources can drift in between. A producer minted five verified
claims at T0; then one source's **content** changed (residue limit 5 → 50 mg/kg)
and one source's **link** repointed to an untrusted origin. A consumer must flag
the now-unsafe claims. (`example_pipeline.py` runs this.)

| consumer | flagged | cost | basis |
|----------|---------|------|-------|
| `reverify()` (treatment) | reg-2, reg-4 — exact | O(1)/claim, 0 tokens, deterministic | sha256 + allowlist |
| Opus (control) | reg-2, reg-4 — correct | a model call, by reasoning | reads & compares |
| Haiku (control) | reg-2, reg-4 — correct | a model call, by reasoning | reads & compares |

**Honest result: no detection gap.** A capable model, *given the drifted sources*,
flagged the same claims — including the link repoint and even a subtler material
edit ("50,000 euro" → "50,000 euro per day"). So the ledger does **not** catch
what a model cannot. Its edge here is narrower and real: it is **deterministic,
zero-model-cost, and auditable** — a hash either matches or it does not, no
judgment call, no per-claim token spend, and the check itself leaves a verifiable
record. For a pipeline re-checking thousands of claims on every run, that is the
difference between a guarantee and a model call you have to trust and pay for.

## The three guarantees

**1. Mechanical provenance integrity — finite and sound.**

| check | defeats |
|-------|---------|
| resolvable `src` (an id in the `SourcePool`) | invented sources |
| verbatim `quote` (exact substring of that source) | fabricated quotes |
| tamper-evident (sha256 `src_hash`, `reverify()` fails closed) | post-hoc edits |
| trusted origin (`require_trusted_link` + allowlist, fails closed) | unaccountable sources |
| `extractive=True` (claim text == quote) | the paraphrase channel |

**2. Reconciliation.** A claim that reuses a prior `key` cannot be recorded
without an explicit `contradicts` / `supersedes` / `refines` edge to an existing
claim. You cannot silently store two conflicting facts.

**3. Semantic faithfulness — one fallible judge, with full context.** Everything
about *meaning* — omission, cherry-picking a sentence while dropping its
qualifier, relation reversal, polarity — is decided by a single
`judge(claim, quote, source)` handed the **entire source**. A judge that sees the
whole document can catch what no local mechanical rule could; it is fallible, and
that is stated plainly rather than papered over with heuristics.

The split is the point: **form is provable, meaning is judged.** well-formedness,
not truth. Trust still bottoms out at "who curates the pool / the allowlist" —
that bottom is irreducible (every chain of trust ends at a root you choose); the
ledger makes it explicit and accountable rather than pretending to remove it.

## Files

- `grounded.py` — the whole thing: `SourcePool`, `GroundedDecoder.cite()`,
  `reverify()`, the `Claim` record, the error types.
- `test_grounded.py` — the guarantees as tests (`PYTHONPATH=. pytest forcing_function/`).
- `example.py` — a runnable example (the working form of the snippet above).

## Prior art (why the citation + reconciliation pairing is a real gap)

A survey of constrained-decoding engines (Outlines, Guidance, XGrammar,
lm-format-enforcer, OpenAI/Anthropic structured outputs), citation methods (RARR,
ALCE, GraphRAG, Perplexity/Gemini), and provenance schemas (nanopublications,
PROV-O, RDF-star, Akoma Ntoso) found the pieces exist separately but not the
combination: structured-output engines can require a `source` *key* to exist but
not that its value is non-empty or *resolves*; citation methods produce or
*evaluate* citations rather than refusing to record an unsourced one; and
**refusing to record two conflicting claims until they are explicitly reconciled
appears to exist nowhere** — the contradiction literature is all post-hoc
benchmarks. This ledger binds both at record-time.
