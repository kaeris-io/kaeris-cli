"""`kaeris check` on Xcode .strings files: no layout warning for the .lproj layout, and the
`$` of a positional specifier (%1$@) is not a price."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaeris import detectors as D  # noqa: E402


def _lproj(tmp_path, src, tgt):
    for lang, text in (("en", src), ("de", tgt)):
        d = tmp_path / f"{lang}.lproj"
        d.mkdir()
        (d / "Localizable.strings").write_text(text, encoding="utf-8")
    return str(tmp_path / "en.lproj" / "Localizable.strings")


def _run(path, langs):
    r = subprocess.run(
        [sys.executable, "-m", "kaeris", "check", "--source", path, "--langs", langs],
        capture_output=True, text=True, env={**os.environ, "NO_COLOR": "1", "PYTHONUTF8": "1"})
    return r.returncode, r.stdout + r.stderr


def test_lproj_layout_gives_no_layout_warning(tmp_path):
    p = _lproj(tmp_path, '"hello" = "Hello";\n', '"hello" = "Hallo";\n')
    code, out = _run(p, "de")
    assert "Could not detect a known locale-file layout" not in out, out
    assert code == 0, out


def test_positional_specifier_dollar_is_not_a_price():
    src = "%1$@ sent you %2$@"
    tgt = "%1$@ hat dir %2$@ gesendet"
    assert D._currency_faults(src, tgt) == []
    assert D._currencies_in(src) == set()


def test_strings_positional_dollar_end_to_end(tmp_path):
    p = _lproj(tmp_path, '"msg" = "%1$@ sent you %2$@";\n',
               '"msg" = "%1$@ hat dir %2$@ gesendet";\n')
    code, out = _run(p, "de")
    assert "currency" not in out, out


def test_real_dollar_price_still_checked():
    assert D._currency_faults("Pay $79", "Zahle 79") != []
