# cli/tests/test_detector_parity.py
"""Proves cli/kaeris/detectors.py is a byte-faithful copy of backend/translator.py:
every ported detector must return IDENTICAL output on a shared corpus. Dev-only —
skips when the backend isn't importable (published package / foreign machine)."""
import os, sys, unittest

def _load_backend():
    here = os.path.dirname(__file__)
    backend = os.path.abspath(os.path.join(here, "..", "..", "backend"))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        import translator  # noqa
        return translator
    except Exception:
        return None

BK = _load_backend()

CORPUS = [  # (original, translated, lang)
    ("Hi %s and %s", "Hola %s", "es"),
    ("Delete 5 files", "Delete 50 files", "ru"),
    ("Total 1,000", "Итого 1.000", "ru"),
    ("Save & exit", "Enregistrer &amp;amp; quitter", "fr"),
    ("{n, plural, one {# item} other {# items}}", "{n, plural, one {# штука}}", "ru"),
    ("{n, plural, one {# item} other {# items}}", "{n, plural, one {# 項目} other {# 項目}}", "ja"),
    ("count 2 things", "عدد ٢ أشياء", "ar"),
    ("Click <b>here</b>", "Cliquez ici", "fr"),
    ("Save changes", "save changes", "ru"),
    # ICU structure vs text. These are the cases where the two copies silently DIVERGED:
    # the backend learned that an ICU block's argument is the placeholder and its arms are
    # not, while the CLI still read arms flatly — so `kaeris check` invented faults the API
    # no longer reported. Parity has to cover the placeholder detectors to catch that.
    ("{gender, select, male {He} female {She} other {They}} updated it",
     "{gender, select, male {Er} female {Sie} other {Sie}} hat es aktualisiert", "de"),
    ("{count} files translated",
     "{count, plural, one {# файл} few {# файла} many {# файлов} other {# файла}}", "ru"),
    ("{count} errors found",
     "{count, plural, zero{لا أخطاء} one{خطأ واحد} two{خطأان} other{# خطأ}}", "ar"),
    ("{count, plural, one {Hi {name}, # file} other {Hi {name}, # files}}",
     "{count, plural, one {Hola, # archivo} other {Hola, # archivos}}", "es"),
    ("Hi {name}", "Hola", "es"),
    ("Order {0:C} for {{user}}", "Bestellung für", "de"),
    # Glossary collapse (found in production, German, glossary=KAERIS): the model answered
    # with the term instead of translating. Both copies must agree on it and on the cases
    # that merely look like it.
    ("How much does it cost?", "KAERIS", "de"),
    ("What makes KAERIS different?", "Was unterscheidet KAERIS?", "de"),
    ("KAERIS Pro", "KAERIS", "de"),
    # Found live 01.08: a short question survived into Russian byte-for-byte (the model
    # reported 98% confidence), and French answered the question in English instead of
    # translating it. Both copies must agree on these and on the brand phrase that must NOT
    # trip them.
    ("How do I get my API key?", "How do I get my API key?", "ru"),
    ("How do I get my API key?", "Как получить мой API-ключ?", "ru"),
    ("GitHub Actions", "GitHub Actions", "ru"),
    ("Which formats do you support?",
     "You can get your API key by signing up for an account on the provider's website. "
     "After registration you will find it in the developer dashboard.", "fr"),
]

# A customer re-run (26.10.2026): an emphasis added, a line break lost, number words that
# compose ("Ninety", "Two hundred"), a label that grew a little.
CORPUS += [
    ("Notes from\nthe *harbor*.", "*港*からの\n*メモ*。", "ja"),
    ("Everything you need\nto review *Northwind*.", "هر آنچه برای بررسی *Northwind* نیاز دارید.", "fa"),
    ("Ninety seconds\nof *setup*.", "90秒の\n*セットアップ*。", "ja"),
    ("Two hundred testers from the forum try the first release.",
     "フォーラムから選ばれた200人のテスターが最初のリリースを試す。", "ja"),
    ("Ninety seconds", "96秒", "ja"),
    ("Build a project\n*with* us.", "আমাদের\n\nসাথে* একটি প্রকল্প তৈরি করুন।", "bn"),
    ("Page not found", "Pahina ay hindi natagpuan", "tl"),
    ("Add to favorites", "Afegeix a la llista de preferits", "ca"),
]

# Plurals by the TARGET language's CLDR forms, nested ones too (p13, 18.11.2026): a plural
# inside a select arm or inside another plural, Welsh, a one-form language, the `one` rule and
# the exact-branch exemption. Both copies must give the same verdict on each.
_SEL = "{g, select, male {{n, plural, %s}} other {{n, plural, %s}}}"
CORPUS += [
    (_SEL % ("one {# item} other {# items}", "one {# item} other {# items}"),
     _SEL % ("one {# plik} other {# pliku}", "one {# plik} few {# pliki} many {# plików} other {# pliku}"), "pl"),
    ("{f, plural, one {# file in {d, plural, one {# dir} other {# dirs}}} other {# files}}",
     "{f, plural, zero {لا} one {ملف {d, plural, one {مجلد} other {# مجلد}}} two {ملفان} few {# ملفات}"
     " many {# ملفًا} other {# ملف}}", "ar"),
    ("{n, plural, one {# item} other {# items}}", "{n, plural, one {# eitem} other {# eitemau}}", "cy"),
    (_SEL % ("one {# item} other {# items}", "one {# item} other {# items}"),
     _SEL % ("other {#個}", "other {#個}"), "ja"),
    ("{n, plural, one {# file} other {# files}}", "{n, plural, other {# Dateien}}", "de"),
    ("{n, plural, =0 {No files} other {# files}}", "{n, plural, =0 {Keine Dateien} other {# Dateien}}", "de"),
    ("{n, plural, =0 {No files} one {# file} other {# files}}",
     "{n, plural, =0 {Нет} =1 {Один файл} other {# файлов}}", "ru"),
    # Variant B (19.11): the same message, two levels. `=0 + other` passed the published 0.2.43
    # (warn now); `few/many/other` without `one` failed it (still an error).
    ("{n, plural, =0 {no files} one {# file} other {# files}}", "{n, plural, =0 {brak} other {# plików}}", "pl"),
    ("{n, plural, one {# file} other {# files}}", "{n, plural, few {# файла} many {# файлов} other {# файла}}", "ru"),
    ("{n, plural, offset:1 =0 {nobody} other {you and # others}}",
     "{n, plural, offset:1 =0 {nikt} other {ty i # innych}}", "pl"),
    ("{n, plural, =0 {none} other {some}}", "{n, plural, =0 {brak}}", "pl"),
    # Round 5 (19.11): `one` only where CLDR has a singular: Cantonese and an unknown code owe none.
    ("{n, plural, one {# file} other {# files}}", "{n, plural, other {# 個檔案}}", "yue"),
    ("{n, plural, one {# file} other {# files}}", "{n, plural, other {# x}}", "xx"),
    ("{n, plural, one {# file} other {# files}}", "{n, plural, other {# x}}", "tl"),
]

GLOSSARY = ["KAERIS"]

@unittest.skipIf(BK is None, "backend/translator.py not importable — parity skipped")
class TestDetectorParity(unittest.TestCase):
    def test_string_detectors_match_backend(self):
        from kaeris import detectors as d
        for src, tr, lang in CORPUS:
            self.assertEqual(d._find_placeholders(src), BK._find_placeholders(src), src)
            self.assertEqual(d._lost_placeholders(src, tr),
                             BK._lost_placeholders(src, tr), (src, tr))
            self.assertEqual(d._placeholder_type_faults(src, tr),
                             BK._placeholder_type_faults(src, tr), (src, tr))
            self.assertEqual(d._numeric_faults(src, tr), BK._numeric_faults(src, tr), (src, tr))
            self.assertEqual(d._entity_faults(src, tr), BK._entity_faults(src, tr), (src, tr))
            self.assertEqual(d._icu_faults(src, tr, lang), BK._icu_faults(src, tr, lang), (src, tr, lang))
            # Variant B (19.11): the level of each ICU finding. /api/check (backend/checker.py)
            # must fail what `kaeris check` fails and warn where it warns.
            self.assertEqual(d._icu_findings(src, tr, lang), BK._icu_findings(src, tr, lang),
                             (src, tr, lang))
            self.assertEqual(d._lost_tags(src, tr), BK._lost_tags(src, tr), (src, tr))
            self.assertEqual(d._untranslated_string(src, tr, lang),
                             BK._untranslated_string(src, tr, lang), (src, tr, lang))
            self.assertEqual(d._lost_glossary(src, tr, GLOSSARY),
                             BK._lost_glossary(src, tr, GLOSSARY), (src, tr))
            self.assertEqual(d._glossary_collapse(src, tr, GLOSSARY),
                             BK._glossary_collapse(src, tr, GLOSSARY), (src, tr))
            self.assertEqual(d._glossary_case_drift(src, tr, GLOSSARY),
                             BK._glossary_case_drift(src, tr, GLOSSARY), (src, tr))
            self.assertEqual(d._answered_instead_of_translating(src, tr),
                             BK._answered_instead_of_translating(src, tr), (src, tr))
            self.assertEqual(d._numeric_faults(src, tr, lang), BK._numeric_faults(src, tr, lang),
                             (src, tr, lang))
            for soft in (False, True):
                self.assertEqual(d._line_break_faults(src, tr, soft),
                                 BK._line_break_faults(src, tr, soft), (src, tr, soft))
            for prose in (False, True):
                self.assertEqual(d._compute_overflow({"k": src}, {"k": tr}, lang, prose=prose),
                                 BK._compute_overflow({"k": src}, {"k": tr}, lang, prose=prose),
                                 (src, tr, lang, prose))

    def test_plural_sets_are_found_alike(self):
        """`translate` adds the forms of exactly the sets `check` judges (0.2.47): the server's
        finder (backend _json_plural_sets) and check._plural_sets must agree on what a set is."""
        from kaeris import check as chk
        if not hasattr(BK, "_json_plural_sets"):
            self.fail("backend has no _json_plural_sets: run it against i18n_tool plural-translate-1121")
        corpus = [
            {"items_one": "a", "items_other": "b", "title": "t"},
            {"cart": "x", "cart.items_one": "a", "cart.items_other": "b", "cart.items_few": "c"},
            {"items.one": "a", "items.other": "b"},
            {"step.one": "a", "step.other": "b", "step.title": "t"},
            {"a.b.one": "a", "a.b.other": "b", "a.b.c.d": "deep"},
            {"lone_other": "x", "only.one": "y"},
            {"place_ordinal_one": "a", "place_ordinal_two": "b", "place_ordinal_other": "c"},
            {"x.zero": "0", "x.one": "1", "x.two": "2", "x.few": "f", "x.many": "m", "x.other": "o"},
            {"k_one": "a", "k_other": "b", "k.one": "c", "k.other": "d"},
        ]
        for flat in corpus:
            mine = {s: set(f) for s, f in chk._plural_sets(flat).items()}
            theirs = {s: set(f) for s, f in BK._json_plural_sets(flat).items()}
            self.assertEqual(mine, theirs, flat)

    def test_the_sets_only_new_completes_are_the_sets_the_server_folds(self):
        """`--only-new` sends a set to be completed only when the server folds it
        (check.plural_set_foldable vs backend _fold_plurals, every_form): one it leaves as it is
        never gets a form, and would be sent and charged for nothing (critic round 4, B7)."""
        from kaeris import check as chk
        corpus = [
            ("{{count}} item", "{{count}} items"),
            ("{{count}} smile :-}", "{{count}} smiles :-}"),
            ("{{count}} :-{", "{{count}} :-{ }"),
            ("{{count}} item for {gender, select, male {him} other {them}}", "{{count}} items"),
            ("{{count}} post in #general", "{{count}} posts in #general"),
            ("One file", "{n, plural, other {# files}}"),
            ("%{count} item", "%{count} items"),
            ("{{count, number}} file", "{{count, number}} files"),
            ("{ {count}", "{count} }"),
            ("x {a, plural, one {b} other {c}}", "y"),
            ("{{count}} item", "{count, selectordinal, one {#st} other {#th}}"),
        ]
        for one, other in corpus:
            flat = {"k_one": one, "k_other": other}
            _, groups = BK._fold_plurals(dict(flat), "json", None, every_form=True)
            self.assertEqual(chk.plural_set_foldable({"one": one, "other": other}), bool(groups),
                             (one, other))

    def test_po_formulas_the_server_writes_are_read(self):
        """`check` reads a .po slot one number selects without the number (formats.
        single_number_slots, 0.2.47 step 2). Every Plural-Forms the server writes must parse,
        give a slot below nplurals, and the loose slots must be the server's zero/one/two
        categories (_PO_SLOT_CATS) — never few/many/other."""
        from kaeris import formats as fm
        for code, (n, expr) in BK._PLURAL_RULES.items():
            header = f"Plural-Forms: nplurals={n}; plural={expr};\n"
            loose = fm.single_number_slots(header)
            self.assertIsNotNone(loose, (code, expr))
            tokens = fm._pf_tokens(expr)
            self.assertTrue(all(0 <= fm._pf_eval(tokens, k) < n for k in range(1001)), (code, expr))
            cats = BK._po_slot_cats(code, n)
            self.assertTrue({cats[i] for i in loose} <= {"zero", "one", "two"}, (code, loose, cats))
            # the file the server writes for this language is read loosely exactly there
            lang = code.replace("-", "_")
            self.assertEqual(fm.po_loose_slots(f"Language: {lang}\n{header}"), loose, code)

    def test_po_gate_table_is_the_servers(self):
        """`check` trusts a .po formula only when it means the same as its language's row of
        formats.PLURAL_RULES (critic 21.11, B2): that table must be the server's _PLURAL_RULES
        (what `translate` writes), row for row."""
        from kaeris import formats as fm
        self.assertEqual(fm.PLURAL_RULES, dict(BK._PLURAL_RULES))
        self.assertEqual(BK._PLURAL_DEFAULT, (2, "(n != 1)"))

    def test_plural_table_snapshot_is_the_servers(self):
        """tests/data/server_plural_tables.json is what the kaeris-cli CI holds the py and npm
        tables to (tests/test_plural_tables_snapshot.py, npm/test/plural-tables-snapshot.test.js).
        Here, with the backend importable (the server's CI, the release machine), it must be the
        server's tables exactly. Refresh: tests/data/refresh_server_plural_tables.py."""
        import json
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(here, "data"))
        from refresh_server_plural_tables import tables
        with open(os.path.join(here, "data", "server_plural_tables.json"), encoding="utf-8") as f:
            snap = json.load(f)
        self.assertEqual(snap, json.loads(json.dumps(tables(BK))))

if __name__ == "__main__":
    unittest.main()
