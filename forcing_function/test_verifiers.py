"""Tests for the generalised claim-to-receipt framework."""
import sys

import pytest

from forcing_function.verifiers import (
    Ledger, Recompute, Command, Quote, Receipt, reverify, Unverified)

PY = sys.executable


def _total(items, shipping, coupon):
    return sum(q * p for q, p in items) + shipping - coupon

ITEMS = [(3, 1299), (1, 4999), (2, 750)]   # 3897+4999+1500 = 10396


# --- recompute: the §13 gain ------------------------------------------------

def test_recompute_refuses_a_wrong_computed_value():
    led = Ledger()
    with pytest.raises(Unverified):
        led.record("c", Recompute("charge 9999", _total,
                                   {"items": ITEMS, "shipping": 0, "coupon": 0}, 9999))
    assert led.receipts == []


def test_recompute_records_the_correct_value_and_reverifies():
    led = Ledger()
    r = led.record("c", Recompute("charge 10396", _total,
                                  {"items": ITEMS, "shipping": 0, "coupon": 0}, 10396))
    assert r.ok and r.evidence["expected"] == 10396
    assert reverify(r, fn=_total) is True


# --- command (execution root) -----------------------------------------------

def test_command_refuses_failing_check():
    led = Ledger()
    with pytest.raises(Unverified):
        led.record("c", Command("it runs", [PY, "-c", "raise SystemExit(1)"]))


def test_command_records_and_reverifies():
    led = Ledger()
    r = led.record("c", Command("it runs", [PY, "-c", "assert True"]))
    assert reverify(r) is True


# --- quote (source root) ----------------------------------------------------

def test_quote_refuses_non_substring():
    led = Ledger()
    with pytest.raises(Unverified):
        led.record("c", Quote("x", "the cat sat", "the dog sat"))


def test_quote_records_and_reverifies_against_source():
    src = "the cat sat on the mat"
    led = Ledger()
    r = led.record("c", Quote("cat sat", src, "cat sat"))
    assert reverify(r, source=src) is True
    assert reverify(r, source="a different source entirely") is False  # digest guard


# --- ledger discipline + heterogeneous receipts -----------------------------

def test_one_ledger_holds_mixed_receipt_kinds():
    led = Ledger()
    led.record("amt", Recompute("=10396", _total,
                                {"items": ITEMS, "shipping": 0, "coupon": 0}, 10396))
    led.record("run", Command("runs", [PY, "-c", "pass"]))
    led.record("cite", Quote("cat", "the cat", "cat"))
    assert {k for _, k, _ in led.summary()} == {"recompute", "command", "quote"}


def test_duplicate_id_refused():
    led = Ledger()
    led.record("c", Command("runs", [PY, "-c", "pass"]))
    with pytest.raises(Unverified):
        led.record("c", Command("again", [PY, "-c", "pass"]))
