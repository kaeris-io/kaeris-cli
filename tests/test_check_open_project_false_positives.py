"""False positives and a misleading message found by running `check` over public projects.

Each case is a minimal synthetic file; none of them names a project.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaeris import check as C  # noqa: E402
from kaeris import cli as K  # noqa: E402
from kaeris import detectors as det  # noqa: E402


def msgs(src, tgt, lang="de"):
    return [f["msg"] for f in det.string_faults(src, tgt, lang)]


# 1. A source with no text has nothing to compare against ------------------------------------
def test_empty_source_value_does_not_make_an_invented_placeholder():
    assert msgs("", "{{name}}已存在", "zh-CN") == []


def test_empty_source_in_a_file_is_no_placeholder_issue():
    r = C.check_locales({"{{name}} exists": ""}, ["zh-CN"], lambda _l: {"{{name}} exists": "{{name}}已存在"})
    assert r["placeholder_issues"] == [] and r["faults"] == [], r
    assert r["ok"] is True


def test_empty_source_still_reports_a_double_encoded_entity():
    assert any("double-encoded entity" in m for m in msgs("", "Speichern &amp;amp; beenden"))


def test_a_real_invented_placeholder_is_still_reported():
    assert any("invented placeholder" in m for m in msgs("Hello", "Hallo {name}"))


# 2. vue-i18n pipe plurals: the language decides how many parts ------------------------------
ARABIC = "{count} سكربت | سكربت واحد | سكربتان | {count} سكربتات | {count} سكربت | {count} سكربت"


def test_pipe_plural_with_six_forms_is_not_a_count_change():
    assert msgs("{count} script | {count} scripts", ARABIC, "ar") == []


def test_pipe_plural_in_a_language_with_one_form_is_clean():
    assert msgs("{count} script | {count} scripts", "{count} 個のスクリプト", "ja") == []


def test_pipe_plural_still_reports_a_lost_placeholder():
    assert "lost placeholder {count}" in msgs("{count} script | {count} scripts", "скрипт | скрипта | скриптов", "ru")


def test_pipe_plural_still_reports_an_invented_placeholder():
    assert any("invented placeholder {total}" in m
               for m in msgs("{count} script | {count} scripts", "{count} Skript | {total} Skripte"))


def test_pipe_plural_still_reports_a_placeholder_repeated_inside_one_form():
    assert any("appears 2×" in m for m in msgs("{count} script | {count} scripts", "{count} {count} Skript | {count} Skripte"))


def test_without_a_pipe_a_repeated_placeholder_is_still_a_fault():
    assert any("appears 2×" in m for m in msgs("{count} script", "{count} {count} Skript"))


# 3. ICU with exact branches and `other` -----------------------------------------------------
EXACT = "{kind, plural, =1{A} =2{B} other{}}"


def test_exact_branches_plus_other_need_no_cldr_forms():
    assert msgs(EXACT, "{kind, plural, =1{А} =2{Б} other{}}", "ru") == []
    assert not any("ICU" in m for m in msgs(EXACT, EXACT, "ar"))


def test_a_real_plural_still_needs_its_cldr_forms():
    got = msgs("{n, plural, one {# file} other {# files}}", "{n, plural, one {# файл} other {# файла}}", "ru")
    assert any("missing the few/many" in m for m in got)


def test_exact_branch_with_one_but_without_few_is_still_reported():
    got = msgs("{n, plural, =0 {none} one {# file} other {# files}}",
               "{n, plural, =0 {нет} one {# файл} other {# файла}}", "ru")
    assert any("few/many" in m for m in got)


# 4. pt_BR / zh_Hans / zh-Hans file names ----------------------------------------------------
def _project(tmp_path, names):
    d = tmp_path / "locales"
    d.mkdir()
    (d / "en.json").write_text(json.dumps({"a": "Hello {name}"}), encoding="utf-8")
    for n in names:
        (d / n).write_text(json.dumps({"a": "Olá {name}"}), encoding="utf-8")
    return d


def _check(d, langs, capsys):
    code = K.main(["check", "--source", str(d / "en.json"), "--langs", langs, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_underscore_region_file_is_found_for_a_hyphen_code(tmp_path, capsys):
    d = _project(tmp_path, ["pt_BR.json"])
    code, rep = _check(d, "pt-BR", capsys)
    assert rep["missing_files"] == [] and code == 0, rep


def test_underscore_script_file_is_found_for_a_hyphen_code(tmp_path, capsys):
    d = _project(tmp_path, ["zh_Hans.json"])
    code, rep = _check(d, "zh-Hans", capsys)
    assert rep["missing_files"] == [] and code == 0, rep


def test_hyphen_script_file_is_found_for_an_underscore_code(tmp_path, capsys):
    d = _project(tmp_path, ["zh-Hans.json"])
    code, rep = _check(d, "zh_Hans", capsys)
    assert rep["missing_files"] == [] and code == 0, rep


def test_lowercase_underscore_file_is_found(tmp_path, capsys):
    d = _project(tmp_path, ["pt_br.json"])
    _, rep = _check(d, "pt-BR", capsys)
    assert rep["missing_files"] == [], rep


def test_prefixed_underscore_file_is_found(tmp_path, capsys):
    d = tmp_path / "l10n"
    d.mkdir()
    (d / "app_en.arb").write_text(json.dumps({"a": "Hello {name}"}), encoding="utf-8")
    (d / "app_pt_BR.arb").write_text(json.dumps({"a": "Olá {name}"}), encoding="utf-8")
    code = K.main(["check", "--source", str(d / "app_en.arb"), "--langs", "pt-BR", "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["missing_files"] == [], rep


def test_an_exact_hyphen_file_wins_over_an_underscore_one(tmp_path, capsys):
    d = _project(tmp_path, ["pt_BR.json"])
    (d / "pt-BR.json").write_text(json.dumps({"a": "Hello"}), encoding="utf-8")
    _, rep = _check(d, "pt-BR", capsys)
    assert any(i["lang"] == "pt-BR" for i in rep["placeholder_issues"]), rep


def test_a_missing_language_is_still_a_missing_file(tmp_path, capsys):
    d = _project(tmp_path, ["pt_BR.json"])
    _, rep = _check(d, "fr", capsys)
    assert rep["missing_files"] == ["fr"], rep


# 5. gettext merge markers in a msgstr ------------------------------------------------------
MARK = "#-#-#-#-#  pt-PT.po (App 2.3.0)  #-#-#-#-#"
MERGED = f"{MARK}\nVerificar Actualizações\n{MARK}\nProcurar actualizações"


def test_merge_markers_get_their_own_message_not_the_model_answered_one():
    got = msgs("Check for updates", MERGED, "pt")
    assert any("merge markers" in m and "gettext" in m for m in got), got
    assert not any("not a translation" in m for m in got), got


def test_numbers_inside_a_merge_marker_are_not_a_number_mismatch():
    got = msgs("Check for updates", MERGED, "pt")
    assert not any(m.startswith("number ") for m in got), got


def test_a_number_outside_the_marker_is_still_compared():
    got = msgs("Delete 5 files", f"{MARK}\nExcluir 50 arquivos", "pt")
    assert any("number 50" in m for m in got), got


def test_a_very_long_answer_without_markers_is_still_called_an_answer():
    got = msgs("How do I get my API key?", "You can get your API key by signing up. " * 6, "fr")
    assert any("not a translation" in m for m in got)
