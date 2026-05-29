# Forcing Function

The one idea worth keeping from the AIDF experiment.

## What this is

A **decode-time forcing function**: a constrained-generation guardrail that makes
an *invalid* model output **un-emittable by construction**, rather than caught by a
validator after the fact. The decoder masks the tokens that would violate the
constraint, so the model literally cannot produce a forbidden sequence.

Two constraints are enforced here:

1. **Provenance** — a claim cannot be *finalized* until it carries a non-empty
   source. You cannot emit a bare assertion.
2. **Reconciliation** — if a claim re-uses a `key` already asserted by an earlier
   claim (i.e. it conflicts), it cannot be finalized until it also emits an
   explicit reconciliation edge (`contradicts` / `supersedes` / `refines`) to a
   resolvable prior claim. You cannot silently store two conflicting facts.

## Why this is the only part that survives

The full AIDF format does not earn its place: for any structure-rich domain a
purpose-built representation already wins (Akoma Ntoso for legislation, an ontology
+ reasoner for conflict detection), and for structure-poor content it degrades to a
thin wrapper. What is *not* redundant is this generation-time guardrail — and it is
~200 lines, not an 11-section format spec.

## The interesting technical split

| constraint     | class            | expressible as a plain grammar? |
|----------------|------------------|---------------------------------|
| provenance     | context-free     | **yes** — see `grammar.gbnf`    |
| reconciliation | context-sensitive| **no** — needs runtime state    |

The provenance half is a context-free constraint, so it can be expressed as a GBNF
grammar usable directly with llama.cpp (or any CFG-constrained decoder). The
reconciliation half depends on *what was emitted earlier in the same document*
(which keys have been seen), which a context-free grammar cannot express. That half
requires a **stateful logit mask** — the thing `constrained_decode.py` demonstrates.
This is precisely where off-the-shelf grammar/structured-output engines stop.

## Files

- `constrained_decode.py` — a model-agnostic stateful decoder. Masks illegal
  next-actions so the two constraints hold by construction. `emit()` is the
  ergonomic entry point a real model calls: it returns a finalized claim, or
  *refuses* (`NeedsProvenance` / `NeedsReconciliation`) until the gap is filled.
- `grammar.gbnf` — the context-free (provenance) half, deployable with llama.cpp.
- `models.py` — toy proposers (adversarial / cooperative) that stand in for an LLM.
- `demo.py` — a narrated run showing the mask block the adversary's shortcuts.
- `claude_in_the_loop.py` — a real model in the loop at the *action* level.
- `test_forcing_function.py` — proves the property.

## Connecting a real model

The Anthropic API exposes no logits, so a model cannot be masked at the *token*
level. It connects at the *action* level instead: the model calls `emit()` with
what it wants to assert, and the call is refused until the claim carries a
non-empty source and (on a conflict) an explicit reconciling edge. At claim
granularity this gives the same guarantee as token masking — an unsourced or
unreconciled claim is never finalized. See `claude_in_the_loop.py`:

```
PYTHONPATH=. python3 forcing_function/claude_in_the_loop.py
```

The token-level path (logit masking) works today only with an open-weights model
via `grammar.gbnf` + llama.cpp, for the context-free provenance half.

## Run

```
PYTHONPATH=. pytest forcing_function/test_forcing_function.py -q
```

## Grounding layer (`grounded.py`): two primitives, nothing in between

An earlier version of this layer grew a middle of half-mechanical heuristics
(whole-sentence, grounded-words, negation-parity). A pentest showed each was both
*unsound* (abbreviation sentence-splits, qualifier omission, off-list polarity
words all bypassed it) and *incomplete* (the residue never ends — every new
polarity word or omission pattern needs another rule). Chasing meaning with
wordlists is a losing, never-ending game, so that middle was **deleted**. Two
clean primitives remain:

**1. Mechanical provenance integrity — finite and sound.** `emit_grounded()` /
`GroundedDecoder.cite()` enforce, unconditionally:

| check | defeats |
|-------|---------|
| resolvable `src` (an id in the `SourcePool`) | invented sources |
| verbatim `quote` (exact substring of that source) | fabricated quotes |
| tamper-evident (sha256 `src_hash`, `reverify()` fails closed) | post-hoc edits |
| trusted origin (link in an allowlist, fails closed) | unaccountable sources |
| `extractive=True` (claim text == quote) | the paraphrase channel |

These are exact, bounded checks — no wordlists, no sentence regex, nothing to
keep patching.

**2. Semantic faithfulness — one fallible judge, with full context.** Everything
about *meaning* — omission, cherry-picking a sentence while dropping its
qualifier, relation reversal, polarity — is decided by a single
`judge(claim, quote, source)` that is handed the **entire source**. A judge that
sees the whole document can catch what no local mechanical rule could; it is
fallible, and that is stated plainly rather than papered over with heuristics.

The split is the whole point: **form is provable, meaning is judged.**
well-formedness, not truth. `GroundedDecoder` is the non-bypassable surface — it
exposes only `cite()`, so there is no ungrounded `emit()` path to forget.

Trust still bottoms out at "who curates the pool / the trusted-domain allowlist."
That bottom is irreducible (every chain of trust ends at a root you choose); the
layer makes it *explicit and accountable* rather than pretending to remove it.

## Prior art (and why this is a real gap)

A survey of constrained-decoding engines (GBNF/llama.cpp, Outlines, Guidance,
XGrammar, lm-format-enforcer, OpenAI/Anthropic structured outputs), citation
methods (RARR, ALCE, GraphRAG, Perplexity/Gemini), and provenance schemas
(nanopublications, PROV-O, RDF-star, Akoma Ntoso) found the pieces exist
separately but the exact combination does not:

- Grammar/structured-output engines enforce *structure*, not semantics. They can
  require a `source` **key** to exist but not that its value is non-empty or
  resolvable — OpenAI Structured Outputs explicitly drops `minLength`/`pattern`,
  pushing that check to post-hoc validation. Here the non-empty + resolvable
  checks live *in the mask*.
- Citation/attribution methods (RARR, ALCE, GraphRAG) produce or *evaluate*
  citations; none make an unsourced claim **un-emittable** at decode time.
- Decode-time **conflict reconciliation** — refusing to emit two conflicting
  claims until an explicit edge is present — appears to exist nowhere; the
  contradiction literature is all post-hoc benchmarks.

So the defensible contribution is narrow and specific: moving the
provenance-and-reconciliation binding from validation-time into the decoder's
masking loop, with resolvability checked as part of the mask.
