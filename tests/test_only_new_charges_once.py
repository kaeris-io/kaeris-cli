"""`--only-new` pays for completing a plural set once, not on every run (critic round 4, B7).

0.2.47 sends a set whole when the target lacks a form its language needs (Polish few/many), so
the server can fold it and write those forms. But the server does not fold every set (a form
with an unbalanced brace, an ICU select inside, a `#` of its own), and a model may lose a form
or write the number `#` where no placeholder can be named the number: then the forms are not
written, the file is the same, and the next run sent — and charged — the same set again, on
every push of the GitHub Action. 0.2.46 said "up to date" and charged 0.

Now:
  * a set the server would not fold is not sent to be completed (check.plural_set_foldable, the
    same conditions as the server's _fold_plurals; tests/test_detector_parity.py compares them);
  * a set sent whole that still lacks a form afterwards is written into kaeris.lock
    (`plural_incomplete`, its source hash) and not sent again to be completed until its source
    changes;
  * a set beside an edited form is sent whole only where that buys forms (the server adds
    them and the language needs a form the set's source lacks); else the edited key goes alone,
    as 0.2.46 sent it.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaeris import check as chk
from kaeris import cli
from kaeris import incremental as inc

SRC = {"cart": {"items_one": "{{count}} item", "items_other": "{{count}} items"}, "title": "Inbox"}
PL_OLD = {"cart": {"items_one": "{{count}} element", "items_other": "{{count}} elementów"},
          "title": "Skrzynka"}


class FormLosingServer:
    """A 0.2.47 server whose model keeps losing Polish `many`: a set sent whole comes back with
    one/few/other only (the server then sends it form by form, as 0.2.46: no few either)."""
    calls = []
    lose = ("few", "many")

    def __init__(self, *a, **kw):
        pass

    def submit(self, filename, content, languages, glossary=None, **kw):
        type(self).calls.append(json.loads(content.decode("utf-8")))
        return f"job-{len(type(self).calls)}"

    def poll(self, job_id, on_progress=None, interval=1.0, max_wait=1800):
        return {"status": "done", "failed_langs": []}

    def download(self, job_id):
        sent = inc.flatten(type(self).calls[int(job_id.rsplit("-", 1)[1]) - 1])
        return {"pl.json": json.dumps(inc.unflatten({k: "PL " + v for k, v in sent.items()}),
                                      ensure_ascii=False).encode()}

    def preview(self, job_id):
        return {}

    def adds_plural_forms(self):
        return True


class OnlyNewPaysOnce(unittest.TestCase):
    def setUp(self):
        FormLosingServer.calls = []
        self._real = cli.KaerisClient
        cli.KaerisClient = FormLosingServer
        self.tmp = tempfile.TemporaryDirectory()
        self.en = os.path.join(self.tmp.name, "en.json")
        self.pl = os.path.join(self.tmp.name, "pl.json")

    def tearDown(self):
        cli.KaerisClient = self._real
        self.tmp.cleanup()

    def _run(self, *extra, langs="pl"):
        buf = io.StringIO()
        args = cli.build_parser().parse_args(
            ["translate", self.en, "--langs", langs, "--only-new", "--no-tm", *extra])
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.cmd_translate(args)
        return code, buf.getvalue()

    def test_a_set_the_server_did_not_complete_is_not_sent_again(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        code, out = self._run("--assume-current")
        self.assertEqual((code, len(FormLosingServer.calls)), (0, 1), out)
        for _ in range(2):
            code, out = self._run()
            self.assertEqual(code, 0, out)
            self.assertEqual(len(FormLosingServer.calls), 1, f"sent and charged again:\n{out}")
            self.assertIn("pl: up to date", out)
            self.assertNotIn("sending", out)

    def test_after_a_source_edit_the_set_is_tried_again(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        self._run("--assume-current")
        self._run()
        edited = json.loads(json.dumps(SRC))
        edited["cart"]["items_other"] = "{{count}} items in your cart"
        inc.dump_json(edited, self.en)
        self._run()
        self.assertEqual(len(FormLosingServer.calls), 2, FormLosingServer.calls)
        self.assertEqual(FormLosingServer.calls[1], {"cart": edited["cart"]})
        self._run()
        self.assertEqual(len(FormLosingServer.calls), 2, "the edit was paid for once")

    def test_the_run_says_the_forms_were_not_added(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        _, out = self._run("--assume-current")
        self.assertIn("not sent again until its source changes", out)


class Foldable(unittest.TestCase):
    """Sets the server leaves as they are (_fold_plurals): not sent to be completed at all."""

    def test_sets_the_server_does_not_fold_are_not_completed(self):
        src = {"smile_one": "{{count}} smile :-}", "smile_other": "{{count}} smiles :-}",
               "g_one": "{{count}} item for {gender, select, male {him} other {them}}",
               "g_other": "{{count}} items for {gender, select, male {him} other {them}}",
               "post_one": "{{count}} post in #general", "post_other": "{{count}} posts in #general",
               "ok_one": "{{count}} file", "ok_other": "{{count}} files"}
        target = {k: "x" for k in src}
        with_todo, to_complete = chk.plural_set_work(src, target, {}, "pl")
        self.assertEqual(with_todo, {})
        self.assertEqual(set(to_complete), {"ok_one", "ok_other"})

    def test_foldable_mirrors_the_server_conditions(self):
        self.assertTrue(chk.plural_set_foldable({"one": "{{count}} a", "other": "{{count}} b"}))
        self.assertFalse(chk.plural_set_foldable({"one": "a :-}", "other": "b"}))
        self.assertFalse(chk.plural_set_foldable({"one": "{x, select, a {b} other {c}}", "other": "d"}))
        self.assertFalse(chk.plural_set_foldable({"one": "#1", "other": "b"}))
        self.assertFalse(chk.plural_set_foldable({"one": ["a"], "other": "b"}))


class EditedFormGoesAloneWhereWholeBuysNothing(unittest.TestCase):
    def test_german_edit_sends_the_edited_key_only(self):
        src = inc.flatten(SRC)
        with_todo, to_complete = chk.plural_set_work(src, dict(src), {"cart.items_other": "x"}, "de")
        self.assertEqual((with_todo, to_complete), ({}, {}))

    def test_without_a_server_that_adds_forms_the_edit_goes_alone(self):
        src = inc.flatten(SRC)
        with_todo, _ = chk.plural_set_work(src, dict(src), {"cart.items_other": "x"}, "pl",
                                           complete=False)
        self.assertEqual(with_todo, {})

    def test_polish_edit_on_a_server_that_adds_forms_sends_the_set(self):
        src = inc.flatten(SRC)
        with_todo, _ = chk.plural_set_work(src, dict(src), {"cart.items_other": "x"}, "pl")
        self.assertEqual(with_todo, {"cart.items_one": "{{count}} item"})


class Marks(unittest.TestCase):
    def test_a_set_still_missing_forms_after_a_send_is_marked(self):
        src = inc.flatten(SRC)
        marks = chk.plural_incomplete_marks(src, inc.flatten(PL_OLD), "pl", set(src))
        self.assertEqual(set(marks), {"cart.items_"})
        full = dict(inc.flatten(PL_OLD), **{"cart.items_few": "a", "cart.items_many": "b"})
        self.assertEqual(chk.plural_incomplete_marks(src, full, "pl", set(src)), {})
        self.assertEqual(chk.plural_incomplete_marks(src, inc.flatten(PL_OLD), "pl", {"title"}), {})


if __name__ == "__main__":
    unittest.main()
