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


# ── 2. review and fix look where translate --verify wrote ────────────────────

def _project(tmp_path, monkeypatch, config=True):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "locales").mkdir()
    (tmp_path / "locales" / "en.json").write_text('{"a": "Hello"}', encoding="utf-8")
    if config:
        (tmp_path / "kaeris.json").write_text(
            json.dumps({"source": "locales/en.json", "langs": ["de"], "out": "locales"}),
            encoding="utf-8")
    (tmp_path / "locales" / "verify.json").write_text('{"de": {"a": "Hello"}}', encoding="utf-8")
    return os.path.join("locales", "verify.json")


class TestVerifyIsFound:

    @pytest.mark.parametrize("config", [True, False])
    def test_review_finds_it(self, tmp_path, monkeypatch, capsys, config):
        where = _project(tmp_path, monkeypatch, config)
        code, out = _run(["review"], capsys)
        assert code == 0, out
        assert where in out, out

    @pytest.mark.parametrize("config", [True, False])
    def test_fix_finds_it(self, tmp_path, monkeypatch, capsys, config):
        where = _project(tmp_path, monkeypatch, config)
        code, out = _run(["fix"], capsys)
        assert code == 0, out
        assert where in out, out

    def test_translate_and_review_agree_on_the_place(self, tmp_path, monkeypatch):
        _project(tmp_path, monkeypatch)
        cfg, _ = K._load_config(type("A", (), {"config": None})())
        assert K.verify_path(cfg.get("out"), ["locales/en.json"]) == os.path.join("locales", "verify.json")
        assert K.verify_path(None, ["locales/en.json"]) == os.path.join(
            os.path.abspath("locales"), "verify.json")

    def test_none_yet_names_the_expected_path(self, tmp_path, monkeypatch, capsys):
        where = _project(tmp_path, monkeypatch)
        os.remove(where)
        for argv in (["review"], ["fix"]):
            code, out = _run(argv, capsys)
            assert code == 2, out
            assert where in out and "--verify" in out, out


# ── 3. what to do next ────────────────────────────────────────────────────────

class TestNextStep:

    def test_check_with_missing_keys_names_the_command(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "en.json").write_text('{"a": "Hello", "b": "Bye"}', encoding="utf-8")
        (tmp_path / "de.json").write_text('{"a": "Hallo"}', encoding="utf-8")
        code, out = _run(["check", "--source", "en.json", "--langs", "de,fr"], capsys)
        assert code == 1, out
        assert "Next: kaeris translate en.json --langs de,fr --only-new" in out, out

    def test_clean_check_has_no_next(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "en.json").write_text('{"a": "Hello"}', encoding="utf-8")
        (tmp_path / "de.json").write_text('{"a": "Hallo"}', encoding="utf-8")
        code, out = _run(["check", "--source", "en.json", "--langs", "de"], capsys)
        assert code == 0 and "Next:" not in out, out

    def test_init_ends_with_one_next(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code, out = _run(["init"], capsys)
        assert code == 0, out
        lines = [l for l in out.splitlines() if l.strip()]
        assert sum("Next:" in l for l in lines) == 1, out
        assert "Next: kaeris translate" in lines[-1], out

    def test_init_comment_is_one_short_line(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        for argv in (["init"], ["init", "--force", "--preset", "next-intl"]):
            _run(argv, capsys)
            note = json.loads((tmp_path / "kaeris.json").read_text(encoding="utf-8"))["//"]
            assert len(note) <= 160, note
            assert "https://kaeris.dev/docs/cli" in note, note


# ── 4. a cp1251 console ───────────────────────────────────────────────────────

_STUB = r"""
import sys
from kaeris import cli as K
K.KaerisClient.languages = lambda self: {"de": "German", "ja": "日本語", "uk": "Українська", "ar": "العربية"}
sys.exit(K.main(sys.argv[1:]))
"""


def _legacy(argv, cwd):
    env = {**os.environ, "PYTHONIOENCODING": "cp1251", "PYTHONUTF8": "0",
           "PYTHONPATH": ROOT, "KAERIS_NO_UPDATE_CHECK": "1", "KAERIS_NO_CTA": "1"}
    env.pop("KAERIS_API_KEY", None)
    return subprocess.run([sys.executable, "-c", _STUB, *argv], capture_output=True, env=env,
                          cwd=str(cwd))


class TestLegacyConsole:

    def test_languages_prints_every_line(self, tmp_path):
        p = _legacy(["languages"], tmp_path)
        assert b"Traceback" not in p.stderr, p.stderr.decode("cp1251", "replace")
        assert p.returncode == 0
        out = p.stdout.decode("cp1251")
        assert "Українська" in out and "German" in out, out
        assert out.count("\n") == 4, out

    def test_marks_are_plain_not_escapes(self, tmp_path):
        p = _legacy(["init"], tmp_path)
        err = p.stderr.decode("cp1251")
        assert p.returncode == 0, err
        assert "\\u" not in err and "\ufffd" not in err, err
        assert "Wrote kaeris.json" in err, err
