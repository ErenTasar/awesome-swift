"""Tests for the execution ledger — completion claims must bind to a receipt.

The guarantee: a claim of "done/verified" is recordable only if a check actually
runs and passes; everything that cannot run, or runs and fails, is refused
(fail-closed). reverify() independently re-runs the receipt.
"""
import sys

import pytest

from forcing_function.verified import (
    ActionLedger, Action, Receipt, reverify, digest, load_ledger,
    UnverifiedClaim, ReceiptMismatch)

PY = sys.executable


# --- the core forcing function ----------------------------------------------

def test_unbacked_claim_is_refused():
    led = ActionLedger()
    with pytest.raises(UnverifiedClaim):
        led.claim("c1", "the script runs cleanly",
                  check=[PY, "-c", "raise SystemExit(1)"])
    assert led.actions == []          # atomic: nothing recorded


def test_backed_claim_is_recorded_with_a_receipt():
    led = ActionLedger()
    a = led.claim("c1", "arithmetic works", check=[PY, "-c", "assert 2 + 2 == 4"])
    assert a.receipt.exit_code == 0 and a.receipt.output_digest
    assert led.summary() == [("c1", "arithmetic works", 0)]


def test_a_nonexistent_command_fails_closed():
    led = ActionLedger()
    with pytest.raises(UnverifiedClaim):
        led.claim("c1", "tool ran", check="this_binary_does_not_exist_xyz --go")
    assert led.actions == []


def test_timeout_fails_closed():
    led = ActionLedger(timeout=1)
    with pytest.raises(UnverifiedClaim):
        led.claim("c1", "finished quickly", check=[PY, "-c", "import time; time.sleep(5)"])


def test_custom_predicate_checks_output_not_just_exit():
    led = ActionLedger()
    # exits 0 but does NOT print the token the assertion is really about:
    with pytest.raises(UnverifiedClaim):
        led.claim("c1", "all tests passed",
                  check=[PY, "-c", "print('1 failed')"],
                  expect=lambda r, out: "0 failed" in out or "passed" in out and "failed" not in out)
    a = led.claim("c2", "all tests passed",
                  check=[PY, "-c", "print('5 passed')"],
                  expect=lambda r, out: "passed" in out and "failed" not in out)
    assert a.id == "c2"


def test_duplicate_id_is_refused():
    led = ActionLedger()
    led.claim("c1", "ok", check=[PY, "-c", "pass"])
    with pytest.raises(UnverifiedClaim):
        led.claim("c1", "again", check=[PY, "-c", "pass"])


# --- reverify: independent re-execution -------------------------------------

def test_reverify_passes_on_a_stable_check():
    led = ActionLedger()
    a = led.claim("c1", "ok", check=[PY, "-c", "assert True"])
    assert reverify(a) is True


def test_reverify_flags_a_regression():
    led = ActionLedger()
    a = led.claim("c1", "exit zero", check=[PY, "-c", "import os; raise SystemExit(0)"])
    # Forge/replace the receipt's command with one that now fails — i.e. the
    # world changed under a recorded claim.
    a.receipt.cmd = f"{PY} -c \"raise SystemExit(3)\""
    with pytest.raises(ReceiptMismatch):
        reverify(a)


def test_reverify_can_require_identical_output():
    led = ActionLedger()
    a = led.claim("c1", "prints a nonce", check=[PY, "-c", "import random; print(random.random())"])
    # same exit code, different stdout each run -> only caught when output is required
    assert reverify(a) is True                      # exit-only: passes
    with pytest.raises(ReceiptMismatch):
        reverify(a, require_same_output=True)


# --- the demonstrated artifact: a claim against a non-existent API ----------

def test_claim_against_a_nonexistent_api_is_refused():
    # The exact class of the project's sharpest artifact (gd.finalized()).
    led = ActionLedger()
    script = ("import json;"
              "json.nonexistent_function()")     # AttributeError at runtime
    with pytest.raises(UnverifiedClaim):
        led.claim("smoke", "the script runs cleanly", check=[PY, "-c", script])
    assert led.actions == []


# --- persistence: receipts survive a handoff to another process ------------

def test_save_load_roundtrip_and_reverify(tmp_path):
    led = ActionLedger()
    led.claim("c1", "math works", check=[PY, "-c", "assert 2+2==4"])
    path = tmp_path / "ledger.json"
    led.save(path)
    loaded = load_ledger(path)
    assert [a.id for a in loaded] == ["c1"]
    assert loaded[0].receipt.cmd == [PY, "-c", "assert 2+2==4"]
    assert reverify(loaded[0]) is True            # re-runs from the loaded receipt


def test_reverify_from_disk_flags_a_regression(tmp_path):
    # Producer records a claim bound to a file; the file then regresses; a
    # consumer that only has the saved ledger still catches it.
    mod = tmp_path / "m.py"
    mod.write_text("def ok():\n    return 1\n")
    led = ActionLedger(cwd=str(tmp_path))
    # -B: never write .pyc, so a re-run always sees current source (hermetic)
    led.claim("ok", "ok() returns 1", check=[PY, "-B", "-c", "from m import ok; assert ok()==1"])
    path = tmp_path / "l.json"
    led.save(path)
    mod.write_text("def ok():\n    return 2\n")    # regression after handoff
    [a] = load_ledger(path)
    with pytest.raises(ReceiptMismatch):
        reverify(a, cwd=str(tmp_path))
