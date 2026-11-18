"""`kaeris check` holds every plural to the CLDR forms of the TARGET language — nested ones too.

A Polish plural with only `one` and `other` renders "5 przedmiotu" for five things: valid ICU,
valid JSON, wrong grammar for every number from 2 up, and no compiler says a word. The check
must fail the build on it (exit 1) in every format that has plurals, including a plural that
sits inside a select or inside another plural, and must stay quiet where the language really
has fewer forms (Japanese: `other` only; English: one/other).

The fixtures are also the corpus of docs/PLURALS-VS-I18NEXT-1118.md, where the same files are
run through `i18next-cli lint`.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(root, source, langs):
    r = subprocess.run(
        [sys.executable, "-m", "kaeris", "check", "--source", str(root / source), "--langs", langs],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
    return r.returncode, r.stdout + r.stderr


def put(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def plural(var, arms):
    """`{var, plural, one {…} other {…}}` from [(category, text), …]."""
    return "{" + var + ", plural, " + " ".join(f"{c} {{{t}}}" for c, t in arms) + "}"


def select(var, arms):
    return "{" + var + ", select, " + " ".join(f"{c} {{{t}}}" for c, t in arms) + "}"


PL_FULL = [("one", "# przedmiot"), ("few", "# przedmioty"), ("many", "# przedmiotów"),
           ("other", "# przedmiotu")]
PL_SHORT = [("one", "# przedmiot"), ("other", "# przedmiotu")]
RU_FULL = [("one", "# предмет"), ("few", "# предмета"), ("many", "# предметов"), ("other", "# предмета")]
AR_FULL = [("zero", "لا عناصر"), ("one", "عنصر واحد"), ("two", "عنصران"), ("few", "# عناصر"),
           ("many", "# عنصرًا"), ("other", "# عنصر")]
AR_SHORT = [("one", "عنصر واحد"), ("other", "# عنصر")]
CY_FULL = [("zero", "# eitemau"), ("one", "# eitem"), ("two", "# eitem"), ("few", "# eitem"),
           ("many", "# eitem"), ("other", "# eitem")]
CY_SHORT = [("one", "# eitem"), ("other", "# eitemau")]
EN_ARMS = [("one", "# item"), ("other", "# items")]
JA_ARMS = [("other", "#個のアイテム")]


def nested_in_select(arms):
    """A plural inside every arm of a gender select — the shape react-intl docs recommend."""
    return select("gender", [("male", "Er: " + plural("count", arms)),
                             ("female", "Sie: " + plural("count", arms)),
                             ("other", plural("count", arms))])


def nested_in_plural(outer, inner):
    """`{files, plural, … {# … in {folders, plural, …}}}` — a plural inside a plural."""
    return plural("files", [(c, t + " / " + plural("folders", inner)) for c, t in outer])


EN_SELECT = nested_in_select(EN_ARMS)
EN_NESTED_PLURAL = nested_in_plural(EN_ARMS, EN_ARMS)

# id -> (source file, {path: text}, target language, missing forms the report must name or
#        None when the files are correct and the check must pass)
CASES = {}


def case(cid, source, files, lang, missing):
    # a target file named like the source would overwrite it and compare the source with itself
    assert source in files and (len(files) > 1 or source.endswith(".xcstrings")), cid
    CASES[cid] = (source, files, lang, missing)


# ── ICU MessageFormat in JSON (next-intl / react-intl / FormatJS), keys nested in objects ──
def icu_json(lang, value):
    return {"en.json": json.dumps({"cart": {"items": EN_SELECT, "flat": plural("count", EN_ARMS),
                                            "deep": EN_NESTED_PLURAL}}, ensure_ascii=False),
            f"{lang}.json": json.dumps({"cart": value}, ensure_ascii=False)}


def icu_value(flat, sel, deep):
    return {"items": nested_in_select(sel), "flat": plural("count", flat), "deep": deep}


case("icu-json pl: flat plural one/other", "en.json",
     icu_json("pl", icu_value(PL_SHORT, PL_FULL, nested_in_plural(PL_FULL, PL_FULL))), "pl", {"few", "many"})
case("icu-json pl: plural inside select one/other", "en.json",
     icu_json("pl", icu_value(PL_FULL, PL_SHORT, nested_in_plural(PL_FULL, PL_FULL))), "pl", {"few", "many"})
case("icu-json pl: plural inside plural one/other", "en.json",
     icu_json("pl", icu_value(PL_FULL, PL_FULL, nested_in_plural(PL_FULL, PL_SHORT))), "pl", {"few", "many"})
case("icu-json pl: complete", "en.json",
     icu_json("pl", icu_value(PL_FULL, PL_FULL, nested_in_plural(PL_FULL, PL_FULL))), "pl", None)
case("icu-json ru: complete", "en.json",
     icu_json("ru", icu_value(RU_FULL, RU_FULL, nested_in_plural(RU_FULL, RU_FULL))), "ru", None)
case("icu-json ar: plural inside plural one/other", "en.json",
     icu_json("ar", icu_value(AR_FULL, AR_FULL, nested_in_plural(AR_FULL, AR_SHORT))), "ar",
     {"zero", "two", "few", "many"})
case("icu-json ar: complete", "en.json",
     icu_json("ar", icu_value(AR_FULL, AR_FULL, nested_in_plural(AR_FULL, AR_FULL))), "ar", None)
case("icu-json cy: flat plural one/other", "en.json",
     icu_json("cy", icu_value(CY_SHORT, CY_FULL, nested_in_plural(CY_FULL, CY_FULL))), "cy",
     {"zero", "two", "few", "many"})
case("icu-json cy: plural inside select one/other", "en.json",
     icu_json("cy", icu_value(CY_FULL, CY_SHORT, nested_in_plural(CY_FULL, CY_FULL))), "cy",
     {"zero", "two", "few", "many"})
case("icu-json cy: complete", "en.json",
     icu_json("cy", icu_value(CY_FULL, CY_FULL, nested_in_plural(CY_FULL, CY_FULL))), "cy", None)
case("icu-json en: control", "en.json",
     icu_json("en-GB", icu_value(EN_ARMS, EN_ARMS, EN_NESTED_PLURAL)), "en-GB", None)
case("icu-json ja: other only, nested", "en.json",
     icu_json("ja", icu_value(JA_ARMS, JA_ARMS, nested_in_plural(JA_ARMS, JA_ARMS))), "ja", None)


# ── i18next JSON v4: key_one / key_few / key_many / key_other, inside nested objects ──
I18N_EN = {"cart": {"item_one": "{{count}} item", "item_other": "{{count}} items"},
           "rank": {"place_ordinal_one": "{{count}}st place", "place_ordinal_two": "{{count}}nd place",
                    "place_ordinal_few": "{{count}}rd place", "place_ordinal_other": "{{count}}th place"}}


def i18n(lang, cart, rank=None):
    return {"en.json": json.dumps(I18N_EN),
            f"{lang}.json": json.dumps({"cart": cart, "rank": rank or {
                "place_ordinal_other": "{{count}}. miejsce"}}, ensure_ascii=False)}


case("i18next pl: _one/_other only", "en.json",
     i18n("pl", {"item_one": "{{count}} przedmiot", "item_other": "{{count}} przedmiotu"}), "pl",
     {"few", "many"})
case("i18next pl: complete (ordinal other only)", "en.json",
     i18n("pl", {"item_one": "{{count}} przedmiot", "item_few": "{{count}} przedmioty",
                 "item_many": "{{count}} przedmiotów", "item_other": "{{count}} przedmiotu"}), "pl", None)
case("i18next ar: _one/_other only", "en.json",
     i18n("ar", {"item_one": "عنصر واحد", "item_other": "{{count}} عنصر"},
          {"place_ordinal_other": "المركز {{count}}"}), "ar", {"zero", "two", "few", "many"})
case("i18next ja: _other only", "en.json",
     i18n("ja", {"item_other": "{{count}}個のアイテム"}, {"place_ordinal_other": "{{count}}位"}), "ja", None)
case("i18next en: control", "en.json",
     {"en.json": json.dumps(I18N_EN), "en-GB.json": json.dumps(I18N_EN)}, "en-GB", None)


# ── Flutter ARB: ICU with a plural inside a select ──
def arb(lang, value):
    meta = {"placeholders": {"gender": {"type": "String"}, "count": {"type": "int"}}}
    return {"app_en.arb": json.dumps({"@@locale": "en", "cartItems": EN_SELECT, "@cartItems": meta}),
            f"app_{lang}.arb": json.dumps({"@@locale": lang, "cartItems": value}, ensure_ascii=False)}


case("arb pl: plural inside select one/other", "app_en.arb", arb("pl", nested_in_select(PL_SHORT)), "pl",
     {"few", "many"})
case("arb pl: complete", "app_en.arb", arb("pl", nested_in_select(PL_FULL)), "pl", None)
case("arb ja: other only", "app_en.arb", arb("ja", nested_in_select(JA_ARMS)), "ja", None)


# ── Xcode String Catalog: a plural inside a substitution, and inside a device variation ──
def _u(v):
    return {"stringUnit": {"state": "translated", "value": v}}


def _pl(arms):
    return {"variations": {"plural": {c: _u(t.replace("#", "%lld")) for c, t in arms}}}


def catalog(lang, arms):
    def sub(a):
        return {"stringUnit": {"state": "translated", "value": "%#@n@"},
                "substitutions": {"n": {"argNum": 1, "formatSpecifier": "lld", **_pl(a)}}}

    def dev(a):
        return {"variations": {"device": {"iphone": _pl(a), "other": _pl(a)}}}

    return {"Localizable.xcstrings": json.dumps({"sourceLanguage": "en", "version": "1.0", "strings": {
        "cart": {"localizations": {"en": sub(EN_ARMS), lang: sub(arms)}},
        "tap": {"localizations": {"en": dev(EN_ARMS), lang: dev(arms)}}}}, ensure_ascii=False)}


case("xcstrings pl: substitution + device plural one/other", "Localizable.xcstrings",
     catalog("pl", PL_SHORT), "pl", {"few", "many"})
case("xcstrings pl: complete", "Localizable.xcstrings", catalog("pl", PL_FULL), "pl", None)
case("xcstrings ja: other only", "Localizable.xcstrings", catalog("ja", JA_ARMS), "ja", None)


# ── Android <plurals> ──
def android(lang, arms):
    def res(a):
        items = "".join(f'<item quantity="{c}">{t.replace("#", "%d")}</item>' for c, t in a)
        return ('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                f'    <plurals name="items">{items}</plurals>\n</resources>\n')
    return {"res/values/strings.xml": res(EN_ARMS), f"res/values-{lang}/strings.xml": res(arms)}


case("android pl: one/other", "res/values/strings.xml", android("pl", PL_SHORT), "pl", {"few", "many"})
case("android ru: complete", "res/values/strings.xml", android("ru", RU_FULL), "ru", None)
case("android ja: other only", "res/values/strings.xml", android("ja", JA_ARMS), "ja", None)


# ── gettext .po: msgstr[n] against the Plural-Forms header ──
def po(lang, nplurals, forms):
    head = ('msgid ""\nmsgstr ""\n"Language: %s\\n"\n"Plural-Forms: nplurals=%d; plural=0;\\n"\n\n')
    src = head % ("en", 2) + 'msgid "%d file"\nmsgid_plural "%d files"\nmsgstr[0] ""\nmsgstr[1] ""\n'
    tgt = head % (lang, nplurals) + 'msgid "%d file"\nmsgid_plural "%d files"\n' + "".join(
        f'msgstr[{i}] "{t}"\n' for i, t in enumerate(forms))
    return {"en.po": src, f"{lang}.po": tgt}


case("po pl: nplurals=3, two msgstr", "en.po", po("pl", 3, ["%d plik", "%d pliki"]), "pl", {"msgstr[2]"})
case("po pl: header nplurals=2", "en.po", po("pl", 2, ["%d plik", "%d pliki"]), "pl", {"nplurals=2"})
case("po ru: complete", "en.po", po("ru", 3, ["%d файл", "%d файла", "%d файлов"]), "ru", None)
case("po ja: nplurals=1", "en.po", po("ja", 1, ["%d 個のファイル"]), "ja", None)


# ── Fluent: a plural selector inside a gender selector ──
def ftl_sel(arms):
    lines = "".join(f"           {'*' if c == 'other' else ' '}[{c}] {t.replace('#', '{ $count }')}\n"
                    for c, t in arms)
    return ("items = { $gender ->\n"
            "        [male] { $count ->\n" + lines + "        }\n"
            "       *[other] { $count ->\n" + lines + "        }\n    }\n")


def ftl(lang, arms):
    return {"en.ftl": ftl_sel(EN_ARMS), f"{lang}.ftl": ftl_sel(arms)}


case("ftl pl: plural inside select one/other", "en.ftl", ftl("pl", PL_SHORT), "pl", {"few", "many"})
case("ftl pl: complete", "en.ftl", ftl("pl", PL_FULL), "pl", None)
case("ftl ja: other only", "en.ftl", ftl("ja", JA_ARMS), "ja", None)


# ── Rails YAML: `one:` / `other:` sub-keys ──
def yml(lang, arms):
    def doc(code, a):
        return f"{code}:\n  cart:\n    items:\n" + "".join(
            f'      {c}: "{t.replace("#", "%{count}")}"\n' for c, t in a)
    return {"en.yml": doc("en", EN_ARMS), f"{lang}.yml": doc(lang, arms)}


case("yaml pl: one/other", "en.yml", yml("pl", PL_SHORT), "pl", {"few", "many"})
case("yaml pl: complete", "en.yml", yml("pl", PL_FULL), "pl", None)
case("yaml ja: other only", "en.yml", yml("ja", JA_ARMS), "ja", None)


@pytest.mark.parametrize("cid", sorted(CASES))
def test_plural_forms_follow_the_target_language(tmp_path, cid):
    source, files, lang, missing = CASES[cid]
    put(tmp_path, files)
    code, out = run(tmp_path, source, lang)
    if missing is None:
        assert code == 0, f"{cid}: a correct plural failed the check\n{out}"
    else:
        assert code == 1, f"{cid}: an incomplete plural passed the check (exit {code})\n{out}"
        for word in missing:
            assert word in out, f"{cid}: the report does not name '{word}'\n{out}"


def test_a_select_is_not_held_to_plural_forms(tmp_path):
    """A gender select in Polish has male/female/other — no CLDR forms are owed there."""
    sel = select("gender", [("male", "On"), ("female", "Ona"), ("other", "Oni")])
    put(tmp_path, {"en.json": json.dumps({"who": select("gender", [("male", "He"), ("female", "She"),
                                                                     ("other", "They")])}),
                   "pl.json": json.dumps({"who": sel}, ensure_ascii=False)})
    code, out = run(tmp_path, "en.json", "pl")
    assert code == 0, out


def test_an_ordinal_inside_a_select_is_not_held_to_cardinal_forms(tmp_path):
    """Polish ordinals have `other` only; the cardinal one/few/many must not be demanded."""
    src = select("g", [("male", "{n, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}"),
                       ("other", "{n, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}")])
    tgt = select("g", [("male", "{n, selectordinal, other {#.}}"), ("other", "{n, selectordinal, other {#.}}")])
    put(tmp_path, {"en.json": json.dumps({"place": src}), "pl.json": json.dumps({"place": tgt})})
    code, out = run(tmp_path, "en.json", "pl")
    assert code == 0, out
