"""i18next plurals are separate keys (item_one / item_few / item_many / item_other). The source
is English (one/other); a Polish file needs few and many as well."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaeris import check as C  # noqa: E402

SRC = {"item_one": "{{count}} file", "item_other": "{{count}} files", "title": "Files"}


def run(target, lang="pl"):
    return C.check_locales(SRC, [lang], lambda _l: target)


def test_polish_without_few_and_many_is_a_fault():
    r = run({"item_one": "{{count}} plik", "item_other": "{{count}} pliku", "title": "Pliki"})
    assert r["ok"] is False
    msgs = " ".join(f["msg"] for f in r["faults"])
    assert "item_few" in msgs and "item_many" in msgs, r


def test_polish_with_all_forms_is_clean_and_not_extra():
    r = run({"item_one": "a {{count}}", "item_few": "b {{count}}", "item_many": "c {{count}}",
             "item_other": "d {{count}}", "title": "Pliki"})
    assert r["ok"] is True, r
    assert r["extra"] == {}, r
    assert r["faults"] == []


def test_german_needs_only_one_and_other():
    r = run({"item_one": "{{count}} Datei", "item_other": "{{count}} Dateien", "title": "Dateien"}, "de")
    assert r["ok"] is True and r["faults"] == [], r


def test_nested_group_and_unrelated_key_named_few_is_still_extra():
    src = {"a": {"x_one": "{{count}} x", "x_other": "{{count}} xs"}, "note": "n"}
    r = C.check_locales(src, ["pl"], lambda _l: {"a": {"x_one": "{{count}} x", "x_other": "{{count}} y"},
                                                 "note": "n", "stray_few": "s"})
    assert r["extra"].get("pl") == ["stray_few"], r
    msgs = " ".join(f["msg"] for f in r["faults"])
    assert "a.x_few" in msgs and "a.x_many" in msgs, r
