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
        self.assertEqual(chk.plural_set_work(src, target, {}, "pl"), {})
        self.assertEqual(chk.plural_set_work({"a_one": "1", "a_other": "2"},
                                             {"a_one": "x", "a_other": "y"}, {}, "ja"), {})


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
