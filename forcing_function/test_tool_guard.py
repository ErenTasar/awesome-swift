"""Tests for the tool-call recompute guard (the §13 fix, end-to-end)."""
import pytest

from forcing_function.tool_guard import GuardedTool, Derived, GuardResult
from forcing_function.verifiers import Ledger, Unverified


def cart_total(items, shipping, coupon):
    return sum(q * p for q, p in items) + shipping - coupon


# the real §13 cart: truth is 33681
CART = {"items": [[3, 1299], [1, 4999], [2, 750], [5, 199], [1, 12500],
                  [4, 325], [2, 1899], [1, 649], [3, 1250], [2, 499]],
        "shipping": 1295, "coupon": 2000}

CHARGE = GuardedTool("charge", computed={
    "total_cents": Derived(cart_total, ["items", "shipping", "coupon"])})


def test_refuses_the_real_wrong_value_from_findings_13():
    args = {**CART, "total_cents": 23734}      # the confidently-wrong emit
    res = CHARGE.validate(args)
    assert res.ok is False
    assert res.corrections == {"total_cents": 33681}
    assert "33681" in res.retry_prompt() and "23734" in res.retry_prompt()


def test_passes_the_correct_value():
    args = {**CART, "total_cents": 33681}
    res = CHARGE.validate(args)
    assert res.ok is True
    assert res.corrections == {}
    assert res.receipts[0][0] == "total_cents"
    assert res.retry_prompt() == ""


def test_enforce_raises_on_wrong_and_returns_on_right():
    with pytest.raises(Unverified):
        CHARGE.enforce({**CART, "total_cents": 1})
    res = CHARGE.enforce({**CART, "total_cents": 33681})
    assert res.ok


def test_dict_input_mapping_when_names_differ():
    def area(width, height):
        return width * height
    tool = GuardedTool("box", computed={
        "area": Derived(area, {"width": "w", "height": "h"})})
    assert tool.validate({"w": 3, "h": 4, "area": 12}).ok
    assert tool.validate({"w": 3, "h": 4, "area": 99}).corrections == {"area": 12}


def test_missing_input_is_a_correction_not_a_silent_pass():
    res = CHARGE.validate({"items": CART["items"], "shipping": 1295,
                           "total_cents": 33681})   # coupon not emitted
    assert res.ok is False
    assert "missing input" in str(res.corrections["total_cents"])


def test_missing_computed_field_is_flagged():
    res = CHARGE.validate(CART)                     # total_cents not emitted
    assert res.ok is False
    assert res.corrections["total_cents"] == "<field not emitted>"


def test_multiple_computed_fields_all_must_pass():
    def subtotal(items):
        return sum(q * p for q, p in items)
    tool = GuardedTool("invoice", computed={
        "subtotal": Derived(subtotal, ["items"]),
        "total": Derived(cart_total, ["items", "shipping", "coupon"])})
    args = {**CART, "subtotal": 999, "total": 33681}   # subtotal wrong, total right
    res = tool.validate(args)
    assert res.ok is False
    assert "subtotal" in res.corrections and "total" not in res.corrections


# --- ledger integration: atomic, only fully-valid calls recorded ------------

def test_valid_call_records_to_ledger():
    led = Ledger()
    CHARGE.validate({**CART, "total_cents": 33681}, ledger=led, id_prefix="call1.")
    assert [cid for cid, _, _ in led.summary()] == ["call1.total_cents"]


def test_invalid_call_records_nothing():
    led = Ledger()
    CHARGE.validate({**CART, "total_cents": 23734}, ledger=led, id_prefix="call1.")
    assert led.receipts == []


# --- fill: the receipt as provider (the §16 abstain case) -------------------

import hashlib

def sha8(s):
    return hashlib.sha256(s.encode()).hexdigest()[:8]

HASHER = GuardedTool("digest", computed={"first8": Derived(sha8, ["s"])})


def test_fill_supplies_a_field_the_model_abstained_on():
    # the §16 scenario: a thinking model honestly leaves a reasoning-impossible
    # field unset (certain:false); fill computes it deterministically.
    out, res = HASHER.fill({"s": "forcing function"})        # first8 absent
    assert res.ok
    assert out["first8"] == "e3fafd48"                       # the real ground truth
    assert res.filled == {"first8": "e3fafd48"}


def test_fill_treats_none_as_abstain():
    out, res = HASHER.fill({"s": "forcing function", "first8": None})
    assert res.ok and out["first8"] == "e3fafd48"
    assert "first8" in res.filled


def test_fill_still_verifies_an_emitted_field_and_refuses_a_wrong_one():
    out, res = HASHER.fill({"s": "forcing function", "first8": "e3fafd48"})
    assert res.ok and res.filled == {}                       # emitted+correct: verified, not filled
    out, res = HASHER.fill({"s": "forcing function", "first8": "deadbeef"})
    assert res.ok is False
    assert res.corrections == {"first8": "e3fafd48"}


def test_fill_records_supplied_value_to_ledger():
    led = Ledger()
    HASHER.fill({"s": "forcing function"}, ledger=led, id_prefix="d.")
    assert led.summary() == [("d.first8", "recompute", "digest.first8 := 'e3fafd48' (supplied)")]


def test_fill_cannot_fill_when_inputs_missing():
    out, res = HASHER.fill({})                               # no `s` to hash
    assert res.ok is False
    assert "missing input" in str(res.corrections["first8"])
