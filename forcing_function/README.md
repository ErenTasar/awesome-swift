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

## Grounding layer (`grounded.py`): from "present" to "resolvable + verbatim"

The base layer forces a non-blank source, but a model under pressure invents one.
`emit_grounded()` hardens provenance against a closed `SourcePool`, converting as
much of "is this citation honest?" into mechanical checks as possible:

| tier | check | defeats | guarantee |
|------|-------|---------|-----------|
| 1 resolvable | `src` is an id in the pool | invented sources | mechanical |
| 2 verbatim | `quote` is an exact substring of the source | fabricated quotes | mechanical |
| 2b whole-sentence | quote is a run of whole sentences | dropping a leading negation (`not guilty`→`guilty`) | mechanical |
| 2c grounded-words | every content word of the claim occurs in the quote | irrelevant quotes / new invented facts | mechanical |
| 2d negation-parity | claim and quote negation cues match | polarity flips using the source's own words | mechanical (heuristic) |
| 3 faithfulness | optional `judge(claim, quote)` | wrong *relation* among shared words | fallible judge |

2c/2d are *necessary, not sufficient* — a claim built only from the quote's
words, with matching polarity, can still misorder a relation; that residue is the
judge's, and the judge is fallible. A red-team (`redteam_grounded.py`) gets every
mechanical attack refused; only judge-residue and pool-poisoning remain.

For pool poisoning, sources are fingerprinted (sha256) and a claim records
`src_hash`; `reverify()` re-checks a claim against the (possibly reloaded) pool
and detects tampering. This makes provenance *tamper-evident*; making it
*trustworthy* needs an external signed root (re-fetch the canonical source at
audit time), which is out of scope for the local layer.

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
