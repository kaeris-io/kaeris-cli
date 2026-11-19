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
    assert found and {lvl for lvl, _, _ in found} == {level}, (sid, found)
    if level == "error":
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


@pytest.mark.parametrize("msg,level", [
    ("ICU plural is missing the one form(s) de requires", det.WARN),
    ("ICU plural is missing the one form(s) fr requires", det.WARN),
    ("ICU plural is missing the few/many/two/zero form(s) cy requires", det.WARN),
    ("ICU plural inside the select arm 'male' is missing the few/many form(s) pl requires", det.WARN),
    ("ICU plural inside the select arm 'male' › plural arm 'one' is missing the one form(s) ru requires", det.WARN),
    ("ICU select inside the plural arm 'one' is missing the required 'other' branch", det.WARN),
    ("ICU plural is missing the few/many form(s) pl requires", det.ERROR),
    ("ICU plural is missing the one form(s) ru requires", det.ERROR),
    ("ICU plural is missing the few/many/two/zero form(s) ar requires", det.ERROR),
    ("ICU plural is missing the required 'other' branch", det.ERROR),
    ("ICU select is missing the required 'other' branch", det.ERROR),
    ("ICU plural/select construct dropped or broken (1 in source, 0 in translation)", det.ERROR),
    ("ICU exact-match branch =0 {…} was dropped in the translation", det.ERROR),
])
def test_icu_fault_severity(msg, level):
    assert det._icu_fault_severity(msg) == level


def test_every_language_of_the_old_table_holds_one():
    """The split by message rests on this: in a 0.2.43 language, any form missing now (the `one`
    rule included) is a form 0.2.43 found missing in the same block."""
    for lang in det._PLURAL_RED_SINCE_043:
        assert "one" in det._CLDR_REQUIRED[lang], lang
    assert set(det._CLDR_REQUIRED) - det._PLURAL_RED_SINCE_043 == {"cy"}


def test_string_faults_carries_the_level():
    got = det.string_faults("{n, plural, one {# file} other {# files}}", "{n, plural, other {# Dateien}}", "de")
    assert got == [{"severity": det.WARN, "msg": "ICU plural is missing the one form(s) de requires"}]
    got = det.string_faults("{n, plural, one {# file} other {# files}}", "{n, plural, one {# plik} other {# pliku}}", "pl")
    assert got == [{"severity": det.ERROR, "msg": "ICU plural is missing the few/many form(s) pl requires"}]
