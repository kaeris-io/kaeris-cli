"""`kaeris translate` writes Xcode's own layout: en.lproj/Localizable.strings -> de.lproj/.

Found 02.11 and reproduced 05.11 on 0.2.43 and 0.2.44: translate fell through to the nested
fallback ("Could not detect a known locale-file layout") and wrote
en.lproj/de/Localizable.strings, a folder Xcode never reads. `check` already looked in
de.lproj (_lproj_sibling), so the two commands disagreed about where the German file lives.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaeris import cli as K  # noqa: E402


def _fresh():
    K._target_path.warned = False


def test_out_path_is_the_sibling_lproj_folder(tmp_path):
    _fresh()
    src = tmp_path / "App" / "en.lproj" / "Localizable.strings"
    src.parent.mkdir(parents=True)
    src.write_text('"save" = "Save";\n', encoding="utf-8")
    got = K._out_path(str(src), "de", None, "en", for_write=True)
    assert os.path.normpath(got) == os.path.normpath(
        str(tmp_path / "App" / "de.lproj" / "Localizable.strings")), got


def test_region_codes_and_stringsdict_keep_xcode_names():
    _fresh()
    src = os.path.join("App", "en.lproj", "Localizable.stringsdict")
    assert K._target_path(src, "pt-BR", None, "en") == os.path.join(
        "App", "pt-BR.lproj", "Localizable.stringsdict")
    assert K._target_path(src, "zh-Hans", None, "en") == os.path.join(
        "App", "zh-Hans.lproj", "Localizable.stringsdict")


def test_out_dir_keeps_the_lproj_folder():
    _fresh()
    src = os.path.join("App", "en.lproj", "Localizable.strings")
    assert K._target_path(src, "de", "build", "en") == os.path.join(
        "build", "de.lproj", "Localizable.strings")


def test_no_unknown_layout_warning(capsys):
    _fresh()
    K._target_path(os.path.join("App", "en.lproj", "Localizable.strings"), "de", None, "en")
    assert "Could not detect" not in capsys.readouterr().err


def test_downloaded_members_land_in_de_lproj(tmp_path):
    """The write step translate runs on the server's archive (members are `<lang><ext>`)."""
    _fresh()
    src = tmp_path / "App" / "en.lproj" / "Localizable.strings"
    src.parent.mkdir(parents=True)
    src.write_text('"save" = "Save";\n', encoding="utf-8")
    written = K._write_members({"de.strings": b'"save" = "Speichern";\n',
                                "ja.strings": b'"save" = "\xe4\xbf\x9d\xe5\xad\x98";\n'},
                               str(src), None, "en")
    de = tmp_path / "App" / "de.lproj" / "Localizable.strings"
    ja = tmp_path / "App" / "ja.lproj" / "Localizable.strings"
    assert de.read_bytes() == b'"save" = "Speichern";\n', written
    assert ja.is_file(), written
    assert not (tmp_path / "App" / "en.lproj" / "de").exists(), written


def test_check_and_translate_agree_on_the_german_file(tmp_path):
    _fresh()
    src = tmp_path / "App" / "en.lproj" / "Localizable.strings"
    src.parent.mkdir(parents=True)
    src.write_text('"save" = "Save";\n', encoding="utf-8")
    sibling = K._lproj_sibling(str(src), "de", "en", None)
    assert os.path.normpath(K._out_path(str(src), "de", None, "en", for_write=True)) == \
        os.path.normpath(sibling)


def test_other_layouts_unchanged():
    _fresh()
    assert K._target_path(os.path.join("locales", "en.json"), "de", None, "en") == \
        os.path.join("locales", "de.json")
    assert K._target_path(os.path.join("locales", "en", "common.json"), "de", None, "en") == \
        os.path.join("locales", "de", "common.json")
    assert K._target_path(os.path.join("res", "values", "strings.xml"), "de", None, "en") == \
        os.path.join("res", "values-de", "strings.xml")
    assert K._target_path(os.path.join("lib", "l10n", "app_en.arb"), "de", None, "en") == \
        os.path.join("lib", "l10n", "app_de.arb")
