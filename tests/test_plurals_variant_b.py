"""Variant B of the plural check (P1.3, 19.11): a plural-form finding 0.2.43 did not report is a
warning; one 0.2.43 did report is still an error.

0.2.45 began to hold every plural to the target language's CLDR forms: the `one` rule for
languages outside the old table (de/fr/es/it: `{n, plural, other {# Dateien}}` renders
"1 Dateien"), plurals nested in a select or another plural, Rails `items.one/other` sets and
Welsh. Upgrading must not turn a CI red that 0.2.43 left green, so those findings say what is
wrong and exit 0; `--strict` fails on them like on every warning. A Polish, Russian or Arabic
plural with one/other only failed in 0.2.43 already and still does.

SAMPLES is also read by the live comparison run (0.2.43 / variant A / variant B, Python and npm),
so the table in the release notes comes from these very files.

"0.2.43" is the release as PUBLISHED on PyPI: its package is commit c9a026e, newer than the git
tag v0.2.43 (572bf51), and it already let a block of `=N` arms + `other` owe no CLDR form.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaeris import detectors as det  # noqa: E402

SRC_ICU = {"files": "{n, plural, one {# file} other {# files}}"}
SRC_SEL = {"files": "{g, select, male {{n, plural, one {# file} other {# files}}} "
                    "other {{n, plural, one {# file} other {# files}}}}"}
SRC_I18N = {"files_one": "{{count}} file", "files_other": "{{count}} files"}


def icu(arms):
    return "{n, plural, " + " ".join(f"{c} {{{t}}}" for c, t in arms) + "}"


def sel(arms):
    return "{g, select, male {" + icu(arms) + "} other {" + icu(arms) + "}}"


def i18n(arms):
    return {f"files_{c}": t.replace("#", "{{count}}") for c, t in arms}


def yml(code, arms):
    return f"{code}:\n  files:\n" + "".join(f'    {c}: "{t.replace("#", "%{count}")}"\n' for c, t in arms)


PL_SHORT = [("one", "# plik"), ("other", "# pliku")]
PL_FULL = [("one", "# plik"), ("few", "# pliki"), ("many", "# plików"), ("other", "# pliku")]
RU_SHORT = [("one", "# файл"), ("other", "# файла")]
RU_FULL = [("one", "# файл"), ("few", "# файла"), ("many", "# файлов"), ("other", "# файла")]
AR_SHORT = [("one", "ملف واحد"), ("other", "# ملف")]
AR_FULL = [("zero", "لا ملفات"), ("one", "ملف واحد"), ("two", "ملفان"), ("few", "# ملفات"),
           ("many", "# ملفًا"), ("other", "# ملف")]
CY_SHORT = [("one", "# ffeil"), ("other", "# ffeiliau")]
DE_FULL = [("one", "# Datei"), ("other", "# Dateien")]
EN_ARMS = [("one", "# file"), ("other", "# files")]


def J(obj):
    return json.dumps(obj, ensure_ascii=False)


# id -> (files, source, langs, expected level of the plural finding in variant B:
#        "error" | "warning" | None for a correct file; extra args)
SAMPLES = {
    "de ICU without one": ({"en.json": J(SRC_ICU), "de.json": J({"files": icu([("other", "# Dateien")])})},
                           "en.json", "de", "warning"),
    "fr ICU without one": ({"en.json": J(SRC_ICU), "fr.json": J({"files": icu([("other", "# fichiers")])})},
                           "en.json", "fr", "warning"),
    "es ICU without one": ({"en.json": J(SRC_ICU), "es.json": J({"files": icu([("other", "# archivos")])})},
                           "en.json", "es", "warning"),
    "it ICU without one": ({"en.json": J(SRC_ICU), "it.json": J({"files": icu([("other", "# file")])})},
                           "en.json", "it", "warning"),
    "de ICU =0 and other": ({"en.json": J({"files": icu([("=0", "no files")] + EN_ARMS)}),
                             "de.json": J({"files": icu([("=0", "keine"), ("other", "# Dateien")])})},
                            "en.json", "de", "warning"),
    "pl ICU one/other": ({"en.json": J(SRC_ICU), "pl.json": J({"files": icu(PL_SHORT)})}, "en.json", "pl", "error"),
    "ru ICU one/other": ({"en.json": J(SRC_ICU), "ru.json": J({"files": icu(RU_SHORT)})}, "en.json", "ru", "error"),
    "ar ICU one/other": ({"en.json": J(SRC_ICU), "ar.json": J({"files": icu(AR_SHORT)})}, "en.json", "ar", "error"),
    "pl i18next _one/_other": ({"en.json": J(SRC_I18N), "pl.json": J(i18n(PL_SHORT))}, "en.json", "pl", "error"),
    "ru i18next _one/_other": ({"en.json": J(SRC_I18N), "ru.json": J(i18n(RU_SHORT))}, "en.json", "ru", "error"),
    "ar i18next _one/_other": ({"en.json": J(SRC_I18N), "ar.json": J(i18n(AR_SHORT))}, "en.json", "ar", "error"),
    "pl ICU inside select one/other": ({"en.json": J(SRC_SEL), "pl.json": J({"files": sel(PL_SHORT)})},
                                       "en.json", "pl", "warning"),
    "pl Rails YAML one/other": ({"en.yml": yml("en", EN_ARMS), "pl.yml": yml("pl", PL_SHORT)}, "en.yml", "pl", "warning"),
    "cy ICU one/other": ({"en.json": J(SRC_ICU), "cy.json": J({"files": icu(CY_SHORT)})}, "en.json", "cy", "warning"),
    "cy i18next _one/_other": ({"en.json": J(SRC_I18N), "cy.json": J(i18n(CY_SHORT))}, "en.json", "cy", "warning"),
    "de ICU full": ({"en.json": J(SRC_ICU), "de.json": J({"files": icu(DE_FULL)})}, "en.json", "de", None),
    "pl ICU full": ({"en.json": J(SRC_ICU), "pl.json": J({"files": icu(PL_FULL)})}, "en.json", "pl", None),
    "ru ICU full": ({"en.json": J(SRC_ICU), "ru.json": J({"files": icu(RU_FULL)})}, "en.json", "ru", None),
    "ar ICU full": ({"en.json": J(SRC_ICU), "ar.json": J({"files": icu(AR_FULL)})}, "en.json", "ar", None),
    "pl i18next full": ({"en.json": J(SRC_I18N), "pl.json": J(i18n(PL_FULL))}, "en.json", "pl", None),
    "pl ICU inside select full": ({"en.json": J(SRC_SEL), "pl.json": J({"files": sel(PL_FULL)})}, "en.json", "pl", None),
}


# ── round 2 (critic, 19.11): the top-level shapes PyPI 0.2.43 passed or failed. The PUBLISHED
# 0.2.43 (= c9a026e, not the tag v0.2.43 = 572bf51) owed no CLDR form at all to a block that spells
# its cases out (`=N` arms and no category keyword besides `other`): `{n, plural, =0 {…} other {…}}`
# passed in Polish. 0.2.45 still owes such a block `one` (unless it has `=1`): a warning in B. ──
def one_key(lang, src, tgt):
    return ({"en.json": J({"files": src}), f"{lang}.json": J({"files": tgt})}, "en.json", lang)


SRC_EQ0 = icu([("=0", "no files")] + EN_ARMS)
SRC_EQ = icu([("=0", "no files"), ("=1", "one file"), ("=2", "two files"), ("other", "# files")])
SRC_OFFSET = "{n, plural, offset:1 =0 {nobody} =1 {you} one {you and # other} other {you and # others}}"
SRC_TWO = SRC_EQ0 + " / " + icu(EN_ARMS).replace("{n,", "{m,")
SRC_ORD = "{n, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}"
SRC_PL_SEL = "{n, plural, one {{g, select, male {his file} other {their file}}} other {# files}}"
for _lang, _zero in (("pl", "brak"), ("ru", "нет"), ("cs", "nic"), ("uk", "немає"), ("he", "אין"),
                     ("lv", "nav"), ("ar", "لا ملفات")):
    SAMPLES[f"{_lang} ICU =0 and other only"] = (
        *one_key(_lang, SRC_EQ0, icu([("=0", _zero), ("other", "# X")])), "warning")
SAMPLES.update({
    "pl ICU =0 =1 and other": (*one_key("pl", SRC_EQ, icu([("=0", "brak"), ("=1", "jeden"), ("=2", "dwa"),
                                                          ("other", "# plików")])), None),
    "ru ICU =1 =2 and other": (*one_key("ru", SRC_EQ, icu([("=0", "нет"), ("=1", "один"), ("=2", "два"),
                                                          ("other", "# файлов")])), None),
    "pl ICU other only": (*one_key("pl", SRC_ICU["files"], icu([("other", "# plików")])), "error"),
    "ru ICU few/many/other without one": (*one_key("ru", SRC_ICU["files"], icu(RU_FULL[1:])), "error"),
    "pl ICU =0 one other": (*one_key("pl", SRC_EQ0, icu([("=0", "brak")] + PL_SHORT)), "error"),
    "pl ICU offset =0 =1 and other": (*one_key("pl", SRC_OFFSET, "{n, plural, offset:1 =0 {nikt} =1 {ty} "
                                                                 "other {ty i # innych}}"), None),
    "pl ICU offset =0 and other": (*one_key("pl", "{n, plural, offset:1 =0 {nobody} other {you and # others}}",
                                            "{n, plural, offset:1 =0 {nikt} other {ty i # innych}}"), "warning"),
    "pl ICU offset one/other": (*one_key("pl", SRC_OFFSET, "{n, plural, offset:1 =0 {nikt} =1 {ty} "
                                                           "one {ty i # inny} other {ty i # innych}}"), "error"),
    "pl ICU =0 without other": (*one_key("pl", icu([("=0", "none"), ("other", "some")]), icu([("=0", "brak")])),
                                {"error", "warning"}),
    "pl two blocks: =0 and other + one/other": (
        *one_key("pl", SRC_TWO, icu([("=0", "brak"), ("other", "# X")]) + " / "
                 + icu(PL_SHORT).replace("{n,", "{m,")), {"error", "warning"}),
    "pl plural one/other with a select inside": (
        *one_key("pl", SRC_PL_SEL, "{n, plural, one {{g, select, male {jego plik} other {ich plik}}} "
                                   "other {# plików}}"), "error"),
    "pl selectordinal other only": (*one_key("pl", SRC_ORD, "{n, selectordinal, other {#.}}"), None),
    "de ICU =0 =1 and other": (*one_key("de", SRC_EQ, icu([("=0", "keine"), ("=1", "eine"), ("=2", "zwei"),
                                                          ("other", "# Dateien")])), None),
    "ja ICU =0 and other": (*one_key("ja", SRC_EQ0, icu([("=0", "なし"), ("other", "#個")])), None),
})

# A run with a real error next to a new plural warning: the error decides, exit 1.
MIXED = {
    "de without one + a missing key": (
        {"en.json": J({**SRC_ICU, "save": "Save"}), "de.json": J({"files": icu([("other", "# Dateien")])})},
        "en.json", "de"),
    "de without one + pl one/other": (
        {"en.json": J(SRC_ICU), "de.json": J({"files": icu([("other", "# Dateien")])}),
         "pl.json": J({"files": icu(PL_SHORT)})}, "en.json", "de,pl"),
}


def put(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def check(root, source, langs, *extra):
    """(exit code, the --json body, the human report) of `kaeris check` from this checkout."""
    env = {**os.environ, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": ROOT,
           "KAERIS_NO_UPDATE_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    base = [sys.executable, "-m", "kaeris", "check", "--source", source, "--langs", langs, *extra]
    j = subprocess.run(base + ["--json"], cwd=root, capture_output=True, text=True, encoding="utf-8", env=env)
    h = subprocess.run(base, cwd=root, capture_output=True, text=True, encoding="utf-8", env=env)
    assert j.returncode == h.returncode, (j.returncode, h.returncode, h.stderr)
    return j.returncode, json.loads(j.stdout), h.stdout + h.stderr


def plural_findings(body):
    """[(level, lang, msg)] of the plural-form findings in a --json body."""
    out = []
    for level, items in (("error", body["faults"]), ("warning", body["warnings"])):
        for f in items:
            if "plural" in f["msg"] or "form(s)" in f["msg"]:
                out.append((level, f["lang"], f["msg"]))
    return out


@pytest.mark.parametrize("sid", sorted(SAMPLES))
def test_new_plural_findings_warn_old_ones_fail(tmp_path, sid):
    files, source, langs, level = SAMPLES[sid]
    put(tmp_path, files)
    code, body, human = check(tmp_path, source, langs)
    found = plural_findings(body)
    if level is None:
        assert code == 0 and not found and not body["warnings"], (sid, body, human)
        assert check(tmp_path, source, langs, "--strict")[0] == 0, sid
        return
    want = level if isinstance(level, set) else {level}
    assert found and {lvl for lvl, _, _ in found} == want, (sid, found)
    if "error" in want:
        assert code == 1 and body["ok"] is False, (sid, code, human)
    else:
        assert code == 0 and body["ok"] is True and not body["faults"], (sid, code, human)
        assert "non-blocking" in human, human
        strict, _, strict_human = check(tmp_path, source, langs, "--strict")
        assert strict == 1, (sid, strict, strict_human)


@pytest.mark.parametrize("mid", sorted(MIXED))
def test_an_error_still_fails_next_to_a_plural_warning(tmp_path, mid):
    files, source, langs = MIXED[mid]
    put(tmp_path, files)
    code, body, human = check(tmp_path, source, langs)
    assert code == 1 and body["ok"] is False, human
    assert ("warning", "de", "ICU plural is missing the one form(s) de requires") in plural_findings(body)


def test_the_warning_is_a_warning_in_sarif(tmp_path):
    files, source, langs, _ = SAMPLES["de ICU without one"]
    put(tmp_path, files)
    code, _, _ = check(tmp_path, source, langs, "--sarif", "out.sarif")
    assert code == 0
    results = json.loads((tmp_path / "out.sarif").read_text(encoding="utf-8"))["runs"][0]["results"]
    assert [(r["ruleId"], r["level"]) for r in results] == [("translation-warning", "warning")], results


_REQUIRED_043 = {  # kaeris/detectors.py _CLDR_REQUIRED as published in 0.2.43 (no Welsh)
    "ru": {"one", "few", "many"}, "uk": {"one", "few", "many"}, "pl": {"one", "few", "many"},
    "cs": {"one", "few"}, "sk": {"one", "few"}, "hr": {"one", "few"}, "sr": {"one", "few"},
    "lt": {"one", "few"}, "ro": {"one", "few"}, "ar": {"zero", "one", "two", "few", "many"},
    "lv": {"zero", "one"}, "sl": {"one", "two", "few"}, "he": {"one", "two"},
}


def icu_faults_043(original, translated, lang):
    """`_icu_faults` of the PUBLISHED 0.2.43 (PyPI = c9a026e), its loop copied verbatim: top-level
    blocks only, the 0.2.43 table, a block of `=N` arms + `other` owes no form."""
    src, tr = det._icu_blocks(original), det._icu_blocks(translated)
    faults = []
    if len(src) > len(tr):
        faults.append("dropped")
    base = (lang or "").replace("_", "-").split("-")[0].lower()
    for typ, seg in tr:
        arms = det._icu_arms(seg)
        if not arms:
            continue
        _, kws, exact_set = arms
        if "other" not in kws:
            faults.append("other")
        if typ == "plural" and not (exact_set and kws <= {"other"}):
            if _REQUIRED_043.get(base, set()) - kws:
                faults.append("forms")
    se = [a[2] for a in (det._icu_arms(s) for _, s in src) if a]
    te = [a[2] for a in (det._icu_arms(s) for _, s in tr) if a]
    if (set().union(*se) if se else set()) - (set().union(*te) if te else set()):
        faults.append("exact")
    return faults


def _corpus():
    """Every top-level shape the critic named and their nesting, in every language that has a
    table entry or a singular: arm sets × =N sets × offset × wrapped in a select or not."""
    import itertools
    arm_sets = [(), ("one",), ("few", "many"), ("one", "few"), ("one", "few", "many"), ("zero", "one", "two"),
                ("zero", "one", "two", "few", "many"), ("two",)]
    exact_sets = [(), ("=0",), ("=1",), ("=0", "=1"), ("=1", "=2"), ("=0", "=2")]
    langs = sorted(_REQUIRED_043) + ["cy", "de", "fr", "en", "ja", "pt-BR"]
    for arms, exacts, other, offset, wrap in itertools.product(arm_sets, exact_sets, (True, False),
                                                               (False, True), (None, "select", "plural")):
        body = " ".join([f"{e} {{x}}" for e in exacts] + [f"{a} {{# x}}" for a in arms] + (["other {# x}"] if other else []))
        block = "{n, plural, " + ("offset:1 " if offset else "") + body + "}"
        src = "{n, plural, " + ("offset:1 " if offset else "") + " ".join(f"{e} {{x}}" for e in exacts) + " one {# x} other {# x}}"
        if wrap == "select":
            block, src = f"{{g, select, male {{{block}}} other {{x}}}}", f"{{g, select, male {{{src}}} other {{x}}}}"
        elif wrap == "plural":
            block = f"{{m, plural, one {{{block}}} few {{a}} many {{b}} other {{c}}}}"
            src = f"{{m, plural, one {{{src}}} other {{c}}}}"
        for lang in langs:
            yield src, block, lang


def test_b_errors_exactly_where_published_043_failed():
    """The promise of B on ICU, string by string: an ICU error now iff published 0.2.43 had one."""
    n = flips = 0
    for src, tgt, lang in _corpus():
        n += 1
        red_043 = bool(icu_faults_043(src, tgt, lang))
        red_b = any(level == det.ERROR for _, level in det._icu_findings(src, tgt, lang))
        assert red_b == red_043, (src, tgt, lang, icu_faults_043(src, tgt, lang), det._icu_findings(src, tgt, lang))
        flips += red_043 != bool(det._icu_faults(src, tgt, lang))
    assert n > 10000 and flips > 100, (n, flips)   # the corpus does hold shapes A fails and 0.2.43 passed


def test_findings_are_the_faults_with_a_level():
    for src, tgt, lang in _corpus():
        found = det._icu_findings(src, tgt, lang)
        assert [m for m, _ in found] == det._icu_faults(src, tgt, lang)
        assert {lvl for _, lvl in found} <= {det.ERROR, det.WARN}


def test_string_faults_carries_the_level():
    got = det.string_faults("{n, plural, one {# file} other {# files}}", "{n, plural, other {# Dateien}}", "de")
    assert got == [{"severity": det.WARN, "msg": "ICU plural is missing the one form(s) de requires"}]
    got = det.string_faults("{n, plural, one {# file} other {# files}}", "{n, plural, one {# plik} other {# pliku}}", "pl")
    assert got == [{"severity": det.ERROR, "msg": "ICU plural is missing the few/many form(s) pl requires"}]


# ── round 5 (critic 4, item 4, 19.11): no `one` is owed where CLDR gives no singular (Cantonese
# `yue` has `other` alone) or has no plural rules at all (an unknown code such as `xx`). B warned
# "missing the one form(s) xx requires" there, and --strict turned that into exit 1 where
# 0.2.43 passed. These go to the npm corpus too (npm/test/gen_baselines.py). ──
YUE_OTHER = [("other", "# 個檔案")]
NO_ONE = {
    "yue ICU other only": one_key("yue", SRC_ICU["files"], icu(YUE_OTHER)),
    "yue ICU inside select other only": ({"en.json": J(SRC_SEL), "yue.json": J({"files": sel(YUE_OTHER)})},
                                         "en.json", "yue"),
    "yue i18next _other only": ({"en.json": J(SRC_I18N), "yue.json": J(i18n(YUE_OTHER))}, "en.json", "yue"),
    "yue-HK ICU other only": one_key("yue-HK", SRC_ICU["files"], icu(YUE_OTHER)),
    "xx ICU other only": one_key("xx", SRC_ICU["files"], icu([("other", "# x")])),
    "xx ICU inside select other only": ({"en.json": J(SRC_SEL), "xx.json": J({"files": sel([("other", "# x")])})},
                                        "en.json", "xx"),
}


@pytest.mark.parametrize("nid", sorted(NO_ONE))
def test_no_one_is_owed_without_a_cldr_singular(tmp_path, nid):
    files, source, langs = NO_ONE[nid]
    put(tmp_path, files)
    code, body, human = check(tmp_path, source, langs)
    assert code == 0 and not plural_findings(body) and not body["warnings"] and not body["faults"], (nid, body, human)
    assert check(tmp_path, source, langs, "--strict")[0] == 0, (nid, human)


def test_the_singular_tables_follow_cldr():
    assert "yue" in det._NO_SINGULAR and not det._HAS_ONE & det._NO_SINGULAR
    assert set(det._CLDR_REQUIRED) <= det._HAS_ONE      # every table language has a `one`
    assert {"en", "de", "fr", "es", "it", "pt", "tr", "fil", "tl"} <= det._HAS_ONE
    assert not {"xx", "yue", "ja", "zh"} & det._HAS_ONE
    assert det._icu_findings(SRC_ICU["files"], icu([("other", "# Dateien")]), "de") == [
        ("ICU plural is missing the one form(s) de requires", det.WARN)]
    # cv/ie/kok have `one` in CLDR 47 (Node 24 Intl), not yet in babel 2.18; the legacy codes
    # CLDR's plurals.json still lists. The whole table was checked against babel 2.18 when it was
    # generated; the backend's test_check_keeps_going.py checks every language KAERIS translates
    # against babel (no babel here: CI allows no skip).
    assert {"cv", "ie", "kok", "tl", "iw", "ji", "mo", "sh"} <= det._HAS_ONE
