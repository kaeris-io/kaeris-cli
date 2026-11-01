"""Two links to the site, with ?utm_source=cli, and nothing else (launch-drafts-1030/cli-cta.md).

- A run the server refuses on a plan limit ends with one stderr line: the pricing page.
- A clean `kaeris check` names the site on every tenth clean run, in a terminal only.
- Neither ever reaches stdout, CI, --json, a pipe; KAERIS_NO_CTA=1 turns both off.

Run through cli.main, the way a person runs it. No network: the client is a stub."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from kaeris import cli, cta
from kaeris.client import KaerisError

PRICING = "https://kaeris.dev/pricing.html?utm_source=cli"
SITE = "https://kaeris.dev/?utm_source=cli"
# The server's sentences (backend/main.py), word for word.
OVER_FILE = ("HTTP 400: File exceeds free tier (12,345 chars, max 10,000). Get a free API key at "
             "kaeris.dev/developer for up to 50,000 chars, or Pro for 200,000 chars.")
OVER_MONTH_API = ("HTTP 429: This run needs 9,000 characters (3 language(s) × the text in your file) "
                  "and 100 are left of your 1,500,000 this month. Translate fewer languages or a "
                  "smaller file to stay inside it — the quota resets on 2026-12-01. To raise it: "
                  "https://kaeris.dev/pricing.html?utm_source=api, or a Lifetime (BYOK) key ...")
NOT_A_LIMIT = "HTTP 500: Translation failed, nothing was charged"


class Tty(io.StringIO):
    def isatty(self):
        return True


class _Stub:
    api_key = "kaerisf_x"

    def config(self):
        return {}

    def key_info(self):
        return {"tier": "free", "char_limit": 50000}

    def languages(self):
        return {"de": "German"}


def _translate(refusal, env=None):
    """`kaeris translate` whose job the server refuses with `refusal`. (exit, stdout, stderr)."""
    cta._limit_said = False
    with tempfile.TemporaryDirectory() as t:
        src = os.path.join(t, "en.json")
        with open(src, "w", encoding="utf-8") as f:
            f.write('{"a": "Hello"}')
        out, errs = io.StringIO(), io.StringIO()
        base = {k: v for k, v in os.environ.items() if k not in ("KAERIS_NO_CTA",)}
        with mock.patch.dict(os.environ, {**base, **(env or {})}, clear=True), \
                mock.patch.object(cli, "_client", return_value=_Stub()), \
                mock.patch.object(cli, "_unknown_langs", return_value=[]), \
                mock.patch.object(cli, "_translate_one", side_effect=KaerisError(refusal)), \
                mock.patch.object(cli, "_update_hint"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(errs):
            code = cli.main(["translate", src, "--langs", "de", "--out", t])
    return code, out.getvalue(), errs.getvalue()


class LimitLine(unittest.TestCase):
    def test_a_refusal_on_a_limit_ends_with_the_pricing_link(self):
        code, out, err = _translate(OVER_FILE)
        self.assertEqual(code, 1)
        self.assertIn("File exceeds free tier", err)
        self.assertIn(f"Limit reached. Plans and limits: {PRICING}", err)
        self.assertEqual(err.count(PRICING), 1)
        self.assertNotIn("kaeris.dev", out)

    def test_another_error_has_no_link(self):
        code, out, err = _translate(NOT_A_LIMIT)
        self.assertEqual(code, 1)
        self.assertNotIn("pricing", err)
        self.assertNotIn("utm_source", err + out)

    def test_the_servers_api_link_is_retagged_and_not_repeated(self):
        _, out, err = _translate(OVER_MONTH_API)
        self.assertNotIn("utm_source=api", err)
        self.assertEqual(err.count(PRICING), 1, err)
        self.assertNotIn("kaeris.dev", out)

    def test_switched_off(self):
        _, out, err = _translate(OVER_FILE, env={"KAERIS_NO_CTA": "1"})
        self.assertIn("File exceeds free tier", err)
        self.assertNotIn(PRICING, err + out)

    def test_said_once_per_run(self):
        cta._limit_said = False
        self.assertEqual(cta.limit_line(OVER_FILE, env={}), cta.LIMIT_LINE)
        self.assertIsNone(cta.limit_line(OVER_FILE, env={}))

    def test_a_rate_limit_is_not_a_plan_limit(self):
        self.assertFalse(cta.is_limit("HTTP 429: Too many requests — still rate-limited after 60s"))


def _check(tmp, stream, env, *extra):
    """`kaeris check` on a clean pair of files. (exit, stdout, stderr)."""
    src = os.path.join(tmp, "en.json")
    if not os.path.exists(src):
        for name in ("en.json", "de.json"):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                f.write('{"a": "Hello {name}"}' if name == "en.json" else '{"a": "Hallo {name}"}')
    out = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(cli, "_update_hint"), \
            mock.patch("sys.stderr", stream), contextlib.redirect_stdout(out):
        code = cli.main(["check", "--source", src, "--langs", "de", *extra])
    return code, out.getvalue(), stream.getvalue()


def _env(tmp, **more):
    keep = {k: v for k, v in os.environ.items()
            if k not in ("CI", "GITHUB_ACTIONS", "KAERIS_NO_CTA", "LOCALAPPDATA", "XDG_CACHE_HOME")}
    cache = os.path.join(tmp, "cache")
    return {**keep, "LOCALAPPDATA": cache, "XDG_CACHE_HOME": cache, **more}


class CheckLine(unittest.TestCase):
    def _runs(self, n, stream_cls=Tty, **more):
        with tempfile.TemporaryDirectory() as t:
            env = _env(t, **more)
            results = [_check(t, stream_cls(), env) for _ in range(n)]
        return results

    def test_every_tenth_clean_run_in_a_terminal(self):
        runs = self._runs(20)
        said = [i + 1 for i, (_, _, err) in enumerate(runs) if SITE in err]
        self.assertEqual(said, [10, 20])
        for code, out, _ in runs:
            self.assertEqual(code, 0)
            self.assertNotIn("kaeris.dev", out)

    def test_not_in_ci(self):
        runs = self._runs(10, CI="true")
        self.assertFalse(any(SITE in err for _, _, err in runs))

    def test_not_into_a_pipe_or_a_log(self):
        runs = self._runs(10, stream_cls=io.StringIO)
        self.assertFalse(any(SITE in err for _, _, err in runs))

    def test_switched_off(self):
        runs = self._runs(10, KAERIS_NO_CTA="1")
        self.assertFalse(any(SITE in err for _, _, err in runs))

    def test_not_with_json(self):
        with tempfile.TemporaryDirectory() as t:
            env = _env(t)
            runs = [_check(t, Tty(), env, "--json") for _ in range(10)]
        for code, out, err in runs:
            self.assertNotIn(SITE, err + out)
            json.loads(out)  # stdout stays one JSON document

    def test_not_after_a_failed_check(self):
        with tempfile.TemporaryDirectory() as t:
            env = _env(t)
            with open(os.path.join(t, "en.json"), "w", encoding="utf-8") as f:
                f.write('{"a": "Hello", "b": "Bye"}')
            with open(os.path.join(t, "de.json"), "w", encoding="utf-8") as f:
                f.write('{"a": "Hallo"}')
            runs = [_check(t, Tty(), env) for _ in range(10)]
        self.assertTrue(all(code == 1 for code, _, _ in runs))
        self.assertFalse(any(SITE in err for _, _, err in runs))


if __name__ == "__main__":
    unittest.main()
