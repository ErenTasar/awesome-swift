# Citation Ledger

The one idea worth keeping from the AIDF experiment, trimmed to what actually
earns its place when you talk to a model through an **API** (no logit access).

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

## Why it is this small

Earlier versions carried a token-mask "decoder" (the software analogue of masking
logits) plus a GBNF grammar and demos. But over an API there are no logits to
mask, so that machine was validation in disguise — and a cross-model A/B eval
(Opus / Sonnet / Haiku, grounded vs. free-form) showed `cite()` delivers the
identical, measurable value in a fraction of the code. So the mask machine, the
grammar and the demos were deleted. What the eval actually credited remains:

- machine-verifiable citations (every quote is provably verbatim), and
- explicit reconciliation of conflicting facts (the shared-`key` → edge rule).

What the eval did **not** credit, stated honestly: with a strong, careful model
the grounded mode produced **no accuracy gain** over a free-form answer that was
already asked to cite. The value here is *auditability and conflict-surfacing*,
not making a capable model more correct. (It did keep a weaker model on-rails in
one run, but that is confounded with the task being framed as a coding task.)

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
- `eval_treatment*.py` — the A/B eval scripts (Opus / Sonnet / Haiku) used to
  decide what to keep; kept as evidence.

## Prior art (why the citation+reconciliation pairing is a real gap)

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
