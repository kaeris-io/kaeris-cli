"""P0.2.47, critic round 3, B4: the server's plural finding never reached the CLI user.

The server names a plural it could not write in every form in `_qa[lang]["plurals"]` ("'%d file':
the answer had no many form; written as before 0.2.47: msgstr[2] (many) repeats msgstr[1] (few)").
`_show_qa` read only `overflow` from `_qa`, so a Polish .po whose msgstr[2] repeated msgstr[1]
came with "✓ Translation QA: no placeholder loss" — and `check` cannot see words, so nothing
said it. Now the finding is printed, and the all-clear line is not.

Exit code: a plural finding is printed like every other QA finding and does not change the exit
code (docs/P047-PLURAL-TRANSLATE.md, round 4): the file is what 0.2.46 wrote.
"""
import io
import types
import unittest.mock as mock

from kaeris import cli as K

PO_REPEAT = ("'%d file': the answer had no many form; written as before 0.2.47: "
             "msgstr[0] (one) holds the singular, msgstr[2] (many) repeats msgstr[1] (few)")


def _qa(preview):
    class _C:
        def preview(self, job):
            return preview

    err, out = io.StringIO(), io.StringIO()
    args = types.SimpleNamespace(verify=False, back_lang="en")
    with mock.patch("sys.stderr", err), mock.patch("sys.stdout", out):
        K._show_qa(_C(), "j", args, "en.po")
    return err.getvalue() + out.getvalue()


def test_a_plural_finding_is_printed():
    said = _qa({"_warnings": {}, "_qa": {"pl": {"plurals": [PO_REPEAT]}, "ru": {"plurals": [PO_REPEAT]}}})
    assert f"[pl] {PO_REPEAT}" in said, said
    assert f"[ru] {PO_REPEAT}" in said, said
    assert "2 plural(s)" in said, said


def test_no_all_clear_line_beside_a_plural_finding():
    said = _qa({"_warnings": {}, "_qa": {"pl": {"plurals": [PO_REPEAT]}}})
    assert "no placeholder loss" not in said, said


def test_a_json_set_missing_forms_is_printed_too():
    msg = "'cart': plural is missing the few/many form(s) pl requires"
    said = _qa({"_warnings": {}, "_qa": {"pl": {"plurals": [msg], "overflow": []}}})
    assert f"[pl] {msg}" in said and "no placeholder loss" not in said, said


def test_nothing_found_still_says_so():
    said = _qa({"_warnings": {}, "_qa": {"pl": {"register": []}}})
    assert "no placeholder loss" in said, said
