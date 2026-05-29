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

- `constrained_decode.py` — a model-agnostic stateful decoder. Given any token
  scorer (a real LLM's logits, or the adversarial mock in the tests), it masks
  illegal next-tokens so the two constraints hold by construction.
- `grammar.gbnf` — the context-free (provenance) half, deployable with llama.cpp.
- `test_forcing_function.py` — proves the property: an adversarial "model" that
  *always tries* to skip the source / skip the reconciliation is structurally
  unable to, and valid documents still generate fine.

## Run

```
PYTHONPATH=. pytest forcing_function/test_forcing_function.py -q
```

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
