"""After `kaeris check` finds missing keys: one line with the command that fills them, about how
many characters that is, and which plan covers it. If Free covers it, the line says so.

The words are pinned in npm/test/cta_fix_cases.json, shared with the JavaScript port. The line
is for a person at a terminal: never in CI, with --json/--sarif/--ci, into a pipe, or with
KAERIS_NO_CTA=1, and never after a clean check. Run through cli.main; no network anywhere."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from kaeris import cli, cta
from kaeris.plans import PLANS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "npm", "test", "cta_fix_cases.json"), encoding="utf-8") as _f:
    CASES = json.load(_f)
URL = CASES["url"]


class Tty(io.StringIO):
    def isatty(self):
        return True


class Words(unittest.TestCase):
    def test_units(self):
        for c in CASES["units"]:
            self.assertEqual(list(cta.gap_units(c["source"], c["missing"], c["incremental"])),
                             c["want"], c)

    def test_commands(self):
        for c in CASES["commands"]:
            self.assertEqual(cta.fix_command(c["langs"], path=c["path"], out=c["out"],
                                             incremental=c["incremental"]), c["want"])

    def test_lines(self):
        for c in CASES["lines"]:
            want = c["want"].replace("CMD", "kaeris translate --langs de --only-new").replace("URL", URL)
            self.assertEqual(cta.fix_text(c["total"], c["largest"],
                                          "kaeris translate --langs de --only-new"), want)

    def test_the_npm_line_names_the_python_package(self):
        line = cta.fix_text(10, 10, "kaeris translate --langs de", npm=True)
        self.assertTrue(line.startswith(CASES["npm_prefix"] + "kaeris translate --langs de,"))

    def test_the_numbers_are_the_plans(self):
        """Every number the line can say comes from kaeris/plans.py, none is typed in cta.py."""
        src = open(os.path.join(ROOT, "kaeris", "cta.py"), encoding="utf-8").read()
        for n in ("1500000", "1_500_000", "12000000", "60000000", "50000", "100000", "$19", "$79"):
            self.assertNotIn(n, src)
        bigger = {k: dict(v) for k, v in PLANS.items()}
        bigger["pro"]["price"] = 21
        self.assertIn("Pro $21/month", cta.fix_text(1_600_000, 10, "x", plans=bigger))

    def test_plain_ascii_and_no_hype(self):
        for c in CASES["lines"]:
            line = cta.fix_text(c["total"], c["largest"], "kaeris translate --langs de")
            line.encode("ascii")  # a cp1252 console prints it
            for word in ("seamless", "unlock", "powered", "AI", "!"):
                self.assertNotIn(word, line)


def _write(tmp, files):
    for name, text in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(text)


GAPS = {"en.json": '{"title": "Welcome, {name}", "cart": {"empty": "Your cart is empty"}, '
                   '"checkout": "Checkout"}',
        "de.json": '{"title": "Willkommen, {name}"}',
        "fr.json": '{"title": "Bienvenue, {name}", "checkout": "Payer"}'}
CLEAN = {"en.json": '{"a": "Hello {name}"}', "de.json": '{"a": "Hallo {name}"}'}


def _check(files, stream=None, env=None, extra=(), langs="de,fr"):
    stream = Tty() if stream is None else stream
    with tempfile.TemporaryDirectory() as t:
        _write(t, files)
        keep = {k: v for k, v in os.environ.items()
                if k not in ("CI", "GITHUB_ACTIONS", "KAERIS_NO_CTA", "LOCALAPPDATA", "XDG_CACHE_HOME")}
        cache = os.path.join(t, "cache")
        out = io.StringIO()
        cwd = os.getcwd()
        os.chdir(t)
        try:
            with mock.patch.dict(os.environ, {**keep, "LOCALAPPDATA": cache, "XDG_CACHE_HOME": cache,
                                              **(env or {})}, clear=True), \
                    mock.patch.object(cli, "_update_hint"), \
                    mock.patch("sys.stderr", stream), contextlib.redirect_stdout(out):
                code = cli.main(["check", "--source", "en.json", "--langs", langs, *extra])
        finally:
            os.chdir(cwd)
    return code, out.getvalue(), stream.getvalue()


class InTheReport(unittest.TestCase):
    def test_missing_keys_end_with_the_fix(self):
        code, out, err = _check(GAPS)
        self.assertEqual(code, 1)
        # de lacks "Your cart is empty" + "Checkout" (26), fr lacks "Your cart is empty" (18).
        want = ("Fix: kaeris translate en.json --langs de,fr --only-new, about 44 characters: "
                f"within Free (1,500,000 a month with a free key). {URL}")
        self.assertEqual(err.rstrip("\n").splitlines()[-1], want)
        self.assertEqual(err.count(URL), 1)
        self.assertNotIn("kaeris.dev", out)

    def test_only_the_languages_with_gaps(self):
        files = {**GAPS, "fr.json": '{"title": "Bienvenue, {name}", "checkout": "Payer", '
                                    '"cart": {"empty": "Vide"}}'}
        _, _, err = _check(files)
        self.assertIn("kaeris translate en.json --langs de --only-new, about 26 characters", err)

    def test_a_missing_file_counts_every_key(self):
        _, _, err = _check({k: v for k, v in GAPS.items() if k != "fr.json"})
        self.assertIn("--langs de,fr --only-new, about 67 characters", err)  # de 26 + fr all 41

    def test_a_whole_file_format_counts_the_whole_file(self):
        po_src = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr "Hello"\n\nmsgid "Bye now"\nmsgstr "Bye now"\n'
        po_de = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr "Hallo"\n'
        with tempfile.TemporaryDirectory() as t:
            _write(t, {"en.po": po_src, "de.po": po_de})
            stream = Tty()
            env = {k: v for k, v in os.environ.items() if k not in ("CI", "KAERIS_NO_CTA")}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(cli, "_update_hint"), mock.patch("sys.stderr", stream), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["check", "--source", os.path.join(t, "en.po"), "--langs", "de",
                                 "--out", t])
        err = stream.getvalue()
        self.assertEqual(code, 1, err)
        line = [l for l in err.splitlines() if l.startswith("Fix: ")]
        self.assertEqual(len(line), 1, err)
        self.assertNotIn("--only-new", line[0])  # .po is sent whole
        self.assertIn("about 12 characters", line[0])  # "Hello" + "Bye now"

    def test_not_after_a_clean_check(self):
        _, _, err = _check(CLEAN, langs="de")
        self.assertNotIn(URL, err)
        self.assertNotIn("Fix:", err)

    def test_not_in_ci(self):
        for env in ({"CI": "true"}, {"CI": "1"}):
            _, _, err = _check(GAPS, env=env)
            self.assertNotIn("Fix:", err)

    def test_not_with_ci_flag_json_or_sarif(self):
        for extra in (("--ci",), ("--json",), ("--sarif", "report.sarif")):
            code, out, err = _check(GAPS, extra=extra)
            self.assertEqual(code, 1)
            self.assertNotIn("Fix:", err + out, extra)
            self.assertNotIn(URL, err + out, extra)
            if extra == ("--json",):
                json.loads(out)

    def test_not_into_a_pipe_or_a_log(self):
        _, _, err = _check(GAPS, stream=io.StringIO())
        self.assertNotIn("Fix:", err)

    def test_switched_off(self):
        _, _, err = _check(GAPS, env={"KAERIS_NO_CTA": "1"})
        self.assertNotIn("Fix:", err)

    def test_nothing_is_sent(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            code, _, err = _check(GAPS)
        self.assertEqual(code, 1)
        self.assertIn("Fix:", err)


if __name__ == "__main__":
    unittest.main()
