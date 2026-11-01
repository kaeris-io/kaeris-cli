"""`kaeris translate --dry-run`: in money terms, not only characters.

On a monthly plan a run has no price of its own: it uses part of the month's volume, and the
bill does not move. The dry run says exactly that, from the numbers the server gave (cap and
what is left), with no price table of ours that could go stale:

  * a run that fits: its share of the month's volume and "no extra charge";
  * a run that does not fit: no promise of "no extra charge";
  * no volume reported (keyless demo, Lifetime, server out of reach): nothing is invented.
"""
import json
import os

import pytest

from kaeris import cli as K
from kaeris import estimate as E

PRO = {"tier": "premium", "model_id": "m1", "char_limit": 100000, "month_cap": 15_000_000,
       "month_used": 12_345, "month_remaining": 14_987_655, "month_resets": "2026-12-01"}


def _stub(monkeypatch, tmp_path, key):
    class Stub:
        api_key = "k"
        openrouter_key = None

        def key_info(self):
            return key

        def config(self):
            return {}

        def languages(self):
            return {"de": "German", "fr": "French"}

        def submit(self, *a, **kw):
            raise AssertionError("a dry run sent a file")

    monkeypatch.setattr(K, "_client", lambda args: Stub())
    monkeypatch.chdir(tmp_path)


def _run(capsys, tmp_path, text_chars, *extra):
    src = os.path.join(str(tmp_path), "en.json")
    with open(src, "w", encoding="utf-8") as f:
        json.dump({"a": "x" * text_chars}, f)
    code = K.main(["translate", "--dry-run", src, "--langs", "de,fr"] + list(extra))
    return code, capsys.readouterr().out


def test_a_run_that_fits_says_its_share_and_no_extra_charge(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, PRO)
    code, out = _run(capsys, tmp_path, 75_000)           # 150,000 of 15,000,000 = 1.00%
    assert code == 0
    assert "1.00% of this month's volume" in out
    assert "No extra charge" in out


def test_a_tiny_run_is_not_rounded_to_zero(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, PRO)
    _, out = _run(capsys, tmp_path, 10)
    assert "less than 0.01% of this month's volume" in out


def test_json_carries_the_share_and_the_extra_charge(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, PRO)
    _, out = _run(capsys, tmp_path, 75_000, "--json")
    vol = json.loads(out)["volume"]
    assert vol["share_percent"] == 1.0
    assert vol["extra_charge_usd"] == 0


def test_a_run_over_the_month_does_not_promise_no_extra_charge(monkeypatch, tmp_path, capsys):
    key = dict(PRO, month_remaining=100)
    _stub(monkeypatch, tmp_path, key)
    _, out = _run(capsys, tmp_path, 75_000)
    assert "No extra charge" not in out
    assert "The server would refuse" in out
    _, out = _run(capsys, tmp_path, 75_000, "--json")
    assert json.loads(out)["volume"]["extra_charge_usd"] is None


def test_no_volume_reported_invents_nothing(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, {"tier": "anonymous", "model_id": "m1", "char_limit": 10000})
    _, out = _run(capsys, tmp_path, 100)
    assert "No extra charge" not in out and "% of" not in out
    _, out = _run(capsys, tmp_path, 100, "--json")
    vol = json.loads(out)["volume"]
    assert vol["share_percent"] is None and vol["extra_charge_usd"] is None


def test_lifetime_names_who_is_paid(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, {"tier": "byok", "model_id": "m1", "char_limit": 1_000_000})
    _, out = _run(capsys, tmp_path, 100)
    assert "OpenRouter" in out and "No extra charge" not in out


def test_the_text_stays_ascii(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, tmp_path, PRO)
    _, out = _run(capsys, tmp_path, 75_000)
    out.encode("ascii")


def test_share_helper():
    assert E.share_percent(150_000, 15_000_000) == 1.0
    assert E.share_percent(5, 0) is None
    assert E.share_percent(5, None) is None
