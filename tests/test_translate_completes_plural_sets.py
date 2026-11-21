"""`--only-new` and the plural forms the server now adds (0.2.47 candidate, round 3 21.11).

The server writes a Polish i18next set as `items_one/_few/_many/_other` (it folds the set into
one ICU string, see i18n_tool test_json_plurals_get_every_form.py). Two things on this side
kept `--only-new` — the GitHub Action's mode — from delivering that:

  * a set counted as up to date when its SOURCE keys were in the target, so a Polish file
    with `items_one/items_other` only (what 0.2.46 wrote) was "up to date" and `check` stayed
    red; and an edit to `items_other` alone sent `items_other` alone, which the server cannot
    fold, so `_few/_many` kept the old wording;
  * a form the source does not have was merged at the ROOT under its dotted name:
    `{"cart.items_few": ...}` next to `{"cart": {...}}`.

Which forms a language needs comes from the same place `kaeris check` reads it
(check._plural_sets / check._language_forms over detectors._CLDR_REQUIRED).
"""
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
PL_FORMS = {"one": "{{count}} element", "few": "{{count}} elementy",
            "many": "{{count}} elementów", "other": "{{count}} elementu"}


class PolishServer:
    """Stands in for KaerisClient: answers like the 0.2.47 server — every i18next set it is
    sent whole comes back in the four Polish forms; any other string comes back prefixed."""
    calls = []

    def __init__(self, *a, **kw):
        pass

    def submit(self, filename, content, languages, glossary=None, **kw):
        PolishServer.calls.append(json.loads(content.decode("utf-8")))
        return f"job-{len(PolishServer.calls)}"

    def poll(self, job_id, on_progress=None, interval=1.0, max_wait=1800):
        return {"status": "done", "failed_langs": []}

    def download(self, job_id):
        sent = inc.flatten(PolishServer.calls[int(job_id.rsplit("-", 1)[1]) - 1])
        out = {}
        for key, val in sent.items():
            base, _, cat = key.rpartition("_")
            if cat in ("one", "other") and f"{base}_one" in sent and f"{base}_other" in sent:
                for c, text in PL_FORMS.items():
                    out[f"{base}_{c}"] = text
            elif cat not in ("one", "other"):
                out[key] = "PL " + val
        return {"pl.json": json.dumps(inc.unflatten(out), ensure_ascii=False).encode()}

    def preview(self, job_id):
        return {}

    def adds_plural_forms(self):
        return True


class ProdServer(PolishServer):
    """The server as it is in production (94114a89): no `plural_forms` in /api/config, and a
    set comes back in the source's own forms only."""

    def adds_plural_forms(self):
        return False

    def download(self, job_id):
        sent = inc.flatten(PolishServer.calls[int(job_id.rsplit("-", 1)[1]) - 1])
        return {"pl.json": json.dumps(inc.unflatten({k: "PL " + v for k, v in sent.items()}),
                                      ensure_ascii=False).encode()}


class OnlyNew(unittest.TestCase):
    def setUp(self):
        PolishServer.calls = []
        self._real = cli.KaerisClient
        cli.KaerisClient = PolishServer
        self.tmp = tempfile.TemporaryDirectory()
        self.en = os.path.join(self.tmp.name, "en.json")
        self.pl = os.path.join(self.tmp.name, "pl.json")

    def tearDown(self):
        cli.KaerisClient = self._real
        self.tmp.cleanup()

    def _run(self, *extra):
        args = cli.build_parser().parse_args(
            ["translate", self.en, "--langs", "pl", "--only-new", "--quiet", "--no-tm", *extra])
        return cli.cmd_translate(args)

    def _check(self):
        res = chk.check_locales(inc.load_json(self.en), ["pl"], lambda l: inc.load_json(self.pl))
        return res["ok"] and not res["warnings"], res

    def test_a_target_missing_polish_forms_is_completed(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        self.assertEqual(self._run("--assume-current"), 0)
        self.assertEqual(len(PolishServer.calls), 1, "the incomplete set is work")
        self.assertEqual(PolishServer.calls[0], {"cart": SRC["cart"]}, "sent whole, title not")
        out = inc.load_json(self.pl)
        self.assertEqual(set(out), {"cart", "title"}, f"a form landed at the root: {out}")
        self.assertEqual(out["cart"], {f"items_{c}": t for c, t in PL_FORMS.items()})
        green, res = self._check()
        self.assertTrue(green, res)

    def test_a_complete_target_is_up_to_date(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json({"cart": {f"items_{c}": t for c, t in PL_FORMS.items()}, "title": "S"},
                      self.pl)
        self.assertEqual(self._run("--assume-current"), 0)
        self.assertEqual(PolishServer.calls, [], "nothing to do must cost nothing")

    def test_an_edit_to_one_form_sends_the_whole_set(self):
        inc.dump_json(SRC, self.en)
        self.assertEqual(self._run(), 0)                      # first run: everything
        PolishServer.calls = []
        edited = json.loads(json.dumps(SRC))
        edited["cart"]["items_other"] = "{{count}} items in your cart"
        inc.dump_json(edited, self.en)
        self.assertEqual(self._run(), 0)
        self.assertEqual(PolishServer.calls, [{"cart": edited["cart"]}])

    def test_ordinals_and_japanese_owe_nothing_more(self):
        """An ordinal set owes `_ordinal_other` only; Japanese has one form."""
        src = {"place_ordinal_one": "{{count}}st", "place_ordinal_other": "{{count}}th"}
        target = {"place_ordinal_one": "{{count}}.", "place_ordinal_other": "{{count}}."}
        self.assertEqual(chk.plural_set_work(src, target, {}, "pl"), ({}, {}))
        self.assertEqual(chk.plural_set_work({"a_one": "1", "a_other": "2"},
                                             {"a_one": "x", "a_other": "y"}, {}, "ja"), ({}, {}))

    def _out(self, *extra):
        import contextlib
        import io
        buf = io.StringIO()
        args = cli.build_parser().parse_args(
            ["translate", self.en, "--langs", "pl", "--only-new", "--no-tm", *extra])
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.cmd_translate(args)
        return code, buf.getvalue()

    def test_completing_a_set_alone_says_so_without_with_them(self):
        """Critic 21.11: "N more key(s) of plural sets sent with them" was printed when nothing
        else was sent — "with them" pointed at nothing."""
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        code, out = self._out("--assume-current")
        self.assertEqual(code, 0, out)
        self.assertNotIn("with them", out)
        self.assertIn("pl: sending 2 key(s) of plural sets whole", out)

    def test_a_set_beside_an_edit_is_sent_with_it(self):
        inc.dump_json(SRC, self.en)
        self.assertEqual(self._run(), 0)
        edited = json.loads(json.dumps(SRC))
        edited["cart"]["items_other"] = "{{count}} items in your cart"
        inc.dump_json(edited, self.en)
        code, out = self._out()
        self.assertIn("pl: 1 more key(s) of plural sets sent with them", out)


class OldServer(unittest.TestCase):
    """CLI 0.2.47 against the production server (94114a89), which never adds a form: critic
    21.11 saw every `--only-new` send the Polish set again and charge it, with no end."""

    def setUp(self):
        PolishServer.calls = []
        self._real = cli.KaerisClient
        cli.KaerisClient = ProdServer
        self.tmp = tempfile.TemporaryDirectory()
        self.en = os.path.join(self.tmp.name, "en.json")
        self.pl = os.path.join(self.tmp.name, "pl.json")

    def tearDown(self):
        cli.KaerisClient = self._real
        self.tmp.cleanup()

    def _run(self, *extra):
        args = cli.build_parser().parse_args(
            ["translate", self.en, "--langs", "pl", "--only-new", "--quiet", "--no-tm", *extra])
        return cli.cmd_translate(args)

    def test_missing_forms_alone_are_not_work_for_a_server_that_does_not_add_them(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        for flags in (("--assume-current",), (), ()):
            self.assertEqual(self._run(*flags), 0)
        self.assertEqual(PolishServer.calls, [], "nothing new: nothing sent, nothing charged")
        self.assertEqual(inc.load_json(self.pl), PL_OLD, "the file is left as it was")

    def test_a_new_key_goes_alone_and_lands_in_place(self):
        inc.dump_json(SRC, self.en)
        inc.dump_json(PL_OLD, self.pl)
        self.assertEqual(self._run("--assume-current"), 0)
        src = json.loads(json.dumps(SRC))
        src["cart"]["saved_one"] = "{{count}} saved"
        src["cart"]["saved_other"] = "{{count}} saved"
        inc.dump_json(src, self.en)
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._run(), 0)
        self.assertEqual(len(PolishServer.calls), 1, PolishServer.calls)
        self.assertEqual(PolishServer.calls[0], {"cart": {"saved_one": "{{count}} saved",
                                                          "saved_other": "{{count}} saved"}})
        out = inc.load_json(self.pl)
        self.assertEqual(set(out), {"cart", "title"}, out)


class Claims(unittest.TestCase):
    def test_the_request_says_this_client_takes_new_forms(self):
        from kaeris.client import KaerisClient
        body, _ = KaerisClient("http://127.0.0.1:9")._multipart("en.json", b"{}", ["pl"])
        self.assertIn(b'name="plurals"\r\n\r\ncldr', body)

    def test_the_server_is_asked_once_whether_it_adds_forms(self):
        from kaeris.client import KaerisClient
        asked = []

        class C(KaerisClient):
            def config(self):
                asked.append(1)
                return {"plural_forms": "cldr"}

        c = C("http://127.0.0.1:9")
        self.assertTrue(c.adds_plural_forms() and c.adds_plural_forms())
        self.assertEqual(len(asked), 1)

        class Old(KaerisClient):
            def config(self):
                return {"max_keys": 1}

        class Down(KaerisClient):
            def config(self):
                raise OSError("no route")

        self.assertFalse(Old("http://127.0.0.1:9").adds_plural_forms())
        self.assertFalse(Down("http://127.0.0.1:9").adds_plural_forms())


class Memory(unittest.TestCase):
    """Critic 21.11: "N of them come from the project memory" counted the Polish set, which the
    server translates again (the memory holds only the source's forms)."""

    def test_sets_a_language_needs_more_forms_of_are_not_remembered_lines(self):
        flat = inc.flatten(SRC)
        self.assertEqual(chk.plural_keys_translated_again(flat, "pl"),
                         {"cart.items_one", "cart.items_other"})
        self.assertEqual(chk.plural_keys_translated_again(flat, "de"), set())
        self.assertEqual(chk.plural_keys_translated_again(flat, "ja"), set())

    def test_the_count_leaves_them_out_only_where_the_server_folds(self):
        hits = {"pl": {"cart.items_one": "a", "cart.items_other": "b", "title": "c"},
                "de": {"cart.items_one": "a", "cart.items_other": "b"}}
        flat = inc.flatten(SRC)
        got, n = cli._without_retranslated(hits, flat, PolishServer())
        self.assertEqual((got, n), ({"pl": {"title": "c"}, "de": hits["de"]}, 3))
        got, n = cli._without_retranslated(hits, flat, ProdServer())
        self.assertEqual((got, n), (hits, 5))


class Merge(unittest.TestCase):
    def test_a_new_form_lands_beside_its_siblings(self):
        src = {"cart": {"items_one": "a", "items_other": "b"},
               "box": {"files": {"one": "a", "other": "b"}}}
        got = inc.merge_translation({}, {"cart": {"items_few": "F"}, "box.files.many": "M"}, src)
        self.assertEqual(got, {"cart": {"items_few": "F"}, "box": {"files": {"many": "M"}}})

    def test_a_flat_source_keeps_flat_keys(self):
        src = {"items.one": "a", "items.other": "b"}
        got = inc.merge_translation({"items.one": "x"}, {"items.few": "F"}, src)
        self.assertEqual(got, {"items.one": "x", "items.few": "F"})


if __name__ == "__main__":
    unittest.main()
