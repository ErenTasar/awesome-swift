"""Auto-bind every computed field of a structured / tool-call output to a Recompute
— the FINDINGS §13 fix made end-to-end.

§13 measured the danger: a value-only / JSON / function-call channel gives a capable
model no room to do the work, so it emits a confidently-wrong *derived* value (a
charge amount, a resource count, a total) — silently, systematically, in the exact
shape a function-calling agent emits as arguments. The single-claim fix is
`verifiers.Recompute`. This wraps it so a *whole tool call* is guarded: declare
which arguments are computed and how, and every emitted derived field is recomputed
from the emitted inputs before the call is allowed. A mismatch refuses the call and
returns a structured, model-readable correction to re-prompt with — instead of
charging the customer the wrong sum.

Trust root: the reference functions, run locally — no provider key, no external
authority (the §4 wall does not apply). Honest scope: it guards fields you *declare*
computed; an undeclared derived field is not checked (the §14 adequacy residue —
the binding is the human's to author). Within-one-pass values need no guard (§11);
the gain is on genuinely computed/stateful fields, which is where §13 bites.
"""
from dataclasses import dataclass, field

from forcing_function.verifiers import Recompute, Unverified


class Derived:
    """A computed output field and how to recompute it. `fn` is the reference
    computation; `inputs` names the emitted arguments it consumes — either a list
    of arg names (fn's parameters share those names) or a {fn_param: arg_name} map
    when they differ."""

    def __init__(self, fn, inputs):
        self.fn, self.inputs = fn, inputs

    def kwargs(self, args):
        """Build fn's keyword arguments from the emitted call args. Raises KeyError
        (with the missing name) if a declared input was not emitted."""
        if isinstance(self.inputs, dict):
            return {param: args[key] for param, key in self.inputs.items()}
        return {name: args[name] for name in self.inputs}


@dataclass
class GuardResult:
    """The outcome of guarding one tool call."""
    ok: bool
    tool: str
    args: dict                              # the emitted args (unchanged)
    receipts: list = field(default_factory=list)       # [(field, Receipt)] that passed
    corrections: dict = field(default_factory=dict)    # field -> expected value / reason
    filled: dict = field(default_factory=dict)         # field -> value supplied for an abstained field

    def retry_prompt(self):
        """A model-readable correction to feed back as the next turn. Empty when ok."""
        if self.ok:
            return ""
        lines = [f"  - {fld}: you emitted {self.args.get(fld, '<missing>')!r}, "
                 f"the correct value is {exp!r}" for fld, exp in self.corrections.items()]
        return (f"The tool call {self.tool!r} has wrong computed field(s). Re-emit "
                f"the call with these corrected values:\n" + "\n".join(lines))


class GuardedTool:
    """Wrap a tool/function-call schema so every declared computed argument is
    auto-recomputed before the call is allowed.

        charge = GuardedTool("charge", computed={
            "total_cents": Derived(cart_total, ["items", "shipping", "coupon"]),
        })
        res = charge.validate(emitted_args)   # res.ok is False if total_cents is wrong
        res = charge.enforce(emitted_args)     # raises Unverified instead
    """

    def __init__(self, name, computed):
        self.name = name
        self.computed = computed              # field name -> Derived

    def _verifier(self, fld, derived, args):
        """Build the Recompute for one field, or None+reason if inputs are missing."""
        try:
            kw = derived.kwargs(args)
        except KeyError as e:
            return None, f"missing input {e.args[0]!r}"
        return Recompute(f"{self.name}.{fld} == {args.get(fld)!r}",
                         derived.fn, kw, args.get(fld)), None

    def validate(self, args, *, ledger=None, id_prefix=""):
        """Recompute every declared computed field of `args`. Returns a GuardResult;
        does not raise. If `ledger` is given and ALL fields pass, each passing field
        is recorded as `{id_prefix}{field}` (atomic: a failing call records nothing,
        so the ledger never holds a half-checked tool call)."""
        receipts, corrections, verifiers = [], {}, []
        for fld, derived in self.computed.items():
            if fld not in args:
                corrections[fld] = "<field not emitted>"
                continue
            verifier, reason = self._verifier(fld, derived, args)
            if verifier is None:
                corrections[fld] = reason
                continue
            r = verifier.check()
            if r.ok:
                receipts.append((fld, r))
                verifiers.append((fld, verifier))
            else:
                corrections[fld] = r.evidence["expected"]
        ok = not corrections
        if ok and ledger is not None:
            for fld, verifier in verifiers:
                ledger.record(f"{id_prefix}{fld}", verifier)
        return GuardResult(ok, self.name, args, receipts, corrections)

    def enforce(self, args, *, ledger=None, id_prefix=""):
        """Like validate, but raise Unverified (with the retry prompt) on any
        mismatch — the fail-closed path for a call site that must not proceed."""
        res = self.validate(args, ledger=ledger, id_prefix=id_prefix)
        if not res.ok:
            raise Unverified(res.retry_prompt())
        return res

    def fill(self, args, *, ledger=None, id_prefix=""):
        """The receipt as *provider*, not just checker — the measured §16 case.

        For each declared computed field: if the model EMITTED it, validate it
        (refuse on mismatch, exactly like validate); if the model ABSTAINED — left
        it missing or None, which a thinking model honestly does for a value it
        cannot compute by reasoning (a hash, a crypto digest, a large product;
        FINDINGS §16: Opus said `certain:false` 4/4 rather than fabricate) — COMPUTE
        it from the emitted inputs and supply it. Returns (filled_args, GuardResult)
        where `result.filled` lists the fields the receipt provided. A field whose
        inputs are themselves missing cannot be filled and becomes a correction.

        This is where the receipt helps a *reasoning-capable* model: it does not
        make the model smarter, it does the one thing the model correctly declined
        to guess — deterministically, locally rooted, zero tokens."""
        out = dict(args)
        receipts, corrections, verifiers, filled = [], {}, [], {}
        for fld, derived in self.computed.items():
            try:
                kw = derived.kwargs(args)
            except KeyError as e:
                corrections[fld] = f"missing input {e.args[0]!r}"   # cannot fill or check
                continue
            computed = derived.fn(**kw)
            if args.get(fld) is None:                 # abstained -> provide it
                out[fld] = computed
                filled[fld] = computed
                r = Recompute(f"{self.name}.{fld} := {computed!r} (supplied)",
                              derived.fn, kw, computed).check()
                receipts.append((fld, r)); verifiers.append((fld, r))
            else:                                     # emitted -> verify it
                if args[fld] == computed:
                    r = Recompute(f"{self.name}.{fld} == {args[fld]!r}",
                                  derived.fn, kw, args[fld]).check()
                    receipts.append((fld, r)); verifiers.append((fld, r))
                else:
                    corrections[fld] = computed
        ok = not corrections
        if ok and ledger is not None:
            for fld, r in verifiers:
                ledger.receipts.append((f"{id_prefix}{fld}", r))
                ledger._ids.add(f"{id_prefix}{fld}")
        res = GuardResult(ok, self.name, out, [(f, r) for f, r in receipts],
                          corrections, filled)
        return out, res
