"""What a newcomer met on 03.11 in an empty folder, one section per stumble.

Every test drives `main(argv)` (or the installed module in a subprocess), not a helper.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaeris import cli as K


def _run(argv, capsys):
    try:
        code = K.main(argv)
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return code, cap.out + cap.err


# ── 1. --to was read as --tone ────────────────────────────────────────────────

class TestNoAbbreviations:

    def test_to_is_the_target_languages(self, monkeypatch, capsys, tmp_path):
        """`--to de,fr` was taken for `--tone` and refused with 15 lines of usage."""
        seen = {}
        monkeypatch.setattr(K, "cmd_translate", lambda a: seen.setdefault("langs", a.langs) and 0)
        code, out = _run(["translate", str(tmp_path / "en.json"), "--to", "de,fr"], capsys)
        assert "invalid choice" not in out, out
        assert seen.get("langs") == "de,fr", out

    def test_check_takes_to_as_well(self, monkeypatch, capsys):
        seen = {}
        monkeypatch.setattr(K, "cmd_check", lambda a: seen.setdefault("langs", a.langs) and 0)
        _run(["check", "--source", "en.json", "--to", "de"], capsys)
        assert seen.get("langs") == "de"

    def test_a_prefix_is_not_a_flag(self, capsys):
        """No parser expands a prefix: `--ton` is an error, not a silent --tone."""
        code, out = _run(["translate", "en.json", "--ton", "formal"], capsys)
        assert code == 2, out
        assert "unrecognized arguments: --ton" in out, out
        code, out = _run(["--ver"], capsys)
        assert code == 2, out
