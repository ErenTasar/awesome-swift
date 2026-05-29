"""Tests for the generalised claim-to-receipt framework."""
import sys

import pytest

from forcing_function.verifiers import (
    Ledger, Recompute, Command, Quote, CrossConsistency, FileAbsent, Receipt,
    reverify, reverify_from_disk, load_ledger, Unverified)

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


# --- persistence + reverify-from-disk (the handoff) -------------------------

def test_save_load_roundtrip_preserves_receipts(tmp_path):
    led = Ledger()
    led.record("amt", Recompute("=10396", _total,
                                {"items": ITEMS, "shipping": 0, "coupon": 0}, 10396))
    led.record("run", Command("runs", [PY, "-c", "pass"]))
    led.record("cite", Quote("cat", "the cat", "cat"))
    p = tmp_path / "led.json"
    led.save(p)
    loaded = load_ledger(p)
    assert [cid for cid, _ in loaded] == ["amt", "run", "cite"]
    assert [r.kind for _, r in loaded] == ["recompute", "command", "quote"]
    assert all(r.ok for _, r in loaded)


def test_reverify_from_disk_command_needs_no_root(tmp_path):
    led = Ledger()
    led.record("run", Command("runs", [PY, "-c", "raise SystemExit(0)"]))
    p = tmp_path / "led.json"
    led.save(p)
    assert reverify_from_disk(p) == [("run", True)]   # re-runs from evidence alone


def test_reverify_from_disk_recompute_and_quote_need_resupplied_roots(tmp_path):
    src = "the cat sat on the mat"
    led = Ledger()
    led.record("amt", Recompute("=10396", _total,
                                {"items": ITEMS, "shipping": 0, "coupon": 0}, 10396))
    led.record("cite", Quote("cat sat", src, "cat sat"))
    p = tmp_path / "led.json"
    led.save(p)
    # roots missing => fail closed, never a silent True
    assert reverify_from_disk(p) == [("amt", False), ("cite", False)]
    # roots re-supplied => passes
    assert reverify_from_disk(p, fns={"amt": _total}, sources={"cite": src}) == \
        [("amt", True), ("cite", True)]


# --- cross-consistency: total == sum(parts) ---------------------------------

def test_cross_refuses_total_that_disagrees_with_its_parts():
    led = Ledger()
    with pytest.raises(Unverified):
        led.record("inv", CrossConsistency("invoice total 9000", [3897, 4999, 1500], 9000))
    assert led.receipts == []


def test_cross_records_and_reverifies(tmp_path):
    led = Ledger()
    r = led.record("inv", CrossConsistency("invoice total 10396", [3897, 4999, 1500], 10396))
    assert r.ok and r.evidence["expected"] == 10396
    assert reverify(r) is True            # default sum, no root needed
    p = tmp_path / "led.json"
    led.save(p)
    assert reverify_from_disk(p) == [("inv", True)]


def test_cross_custom_agg():
    led = Ledger()
    r = led.record("cnt", CrossConsistency("item count 3", [[1], [2], [3]], 3, agg=len))
    assert r.ok
    assert reverify(r, agg=len) is True


# --- file-absent: 'I updated every call-site' -------------------------------

def test_file_absent_refuses_when_pattern_present(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = old_api()\ny = old_api()\n")
    led = Ledger()
    with pytest.raises(Unverified) as ei:
        led.record("migrated", FileAbsent("removed all old_api calls",
                                          r"\bold_api\b", [str(f)]))
    assert "still present" in str(ei.value)


def test_file_absent_records_when_clean_and_reverifies(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = new_api()\n")
    led = Ledger()
    r = led.record("migrated", FileAbsent("removed all old_api calls",
                                          r"\bold_api\b", [str(f)]))
    assert r.ok
    p = tmp_path / "led.json"
    led.save(p)
    assert reverify_from_disk(p) == [("migrated", True)]   # path rides in the receipt
    # a regression that reintroduces the pattern is caught on reverify
    f.write_text("x = old_api()\n")
    assert reverify_from_disk(p) == [("migrated", False)]


def test_file_absent_missing_scanned_file_is_a_defect_not_a_pass():
    led = Ledger()
    with pytest.raises(Unverified):
        led.record("m", FileAbsent("clean", r"x", ["/no/such/file/here.py"]))


def test_recompute_survives_tuple_to_list_json_roundtrip(tmp_path):
    """The handoff's named pitfall: ITEMS is a list of tuples; JSON has no tuple,
    so it reloads as lists. reverify must still hold (a stale-pitfall guard)."""
    led = Ledger()
    led.record("amt", Recompute("=10396", _total,
                                {"items": ITEMS, "shipping": 0, "coupon": 0}, 10396))
    p = tmp_path / "led.json"
    led.save(p)
    _, r = load_ledger(p)[0]
    assert r.evidence["inputs"]["items"] == [[3, 1299], [1, 4999], [2, 750]]  # tuples gone
    assert reverify(r, fn=_total) is True   # _total unpacks lists too
