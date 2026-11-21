"""P0.2.47 step 2 (21.11): once `translate` wrote every Arabic .po slot with its own form,
`kaeris check` failed our own output: msgstr[1] is read against msgid_plural, and Arabic's
msgstr[1] is the `one` slot — "رسالة واحدة" ("one message") is correct without the number.

`check` lets a slot the file's Plural-Forms formula picks for exactly ONE n in 0..1000 leave the
number out (Arabic zero/one/two = 0/1/2, Hebrew two = 2). A slot that covers many numbers must
keep it. Critic 21.11 (B2): only when the formula is sound (every slot it gives exists) and gives
the same slot for every n as the formula of the file's Language in the server's table
(formats.PLURAL_RULES); `plural=n`, Hebrew's formula in a Russian file and the like stay strict.
gettext's `msgfmt -c` is looser (a slot picked for fewer than 5 values of n passes, and it does
not compare the formula with the language): docs/p047/harness/b2_msgfmt.py sets the two side by
side.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaeris import formats as fm  # noqa: E402

SRC = ('msgid ""\nmsgstr ""\n"Language: en\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'
       'msgid "One message"\nmsgid_plural "%d messages"\nmsgstr[0] ""\nmsgstr[1] ""\n\n'
       'msgid "%d file"\nmsgid_plural "%d files"\nmsgstr[0] ""\nmsgstr[1] ""\n')

AR = "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);"
PL = "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"
RU = "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"
CS = "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;"
HE = "nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);"
SL = "nplurals=4; plural=(n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3);"
LV = "nplurals=3; plural=(n%10==0 || (n%100>=11 && n%100<=19) ? 0 : n%10==1 && n%100!=11 ? 1 : 2);"
JA = "nplurals=1; plural=0;"


def target(lang, forms_msg, forms_file, rule):
    head = (f'msgid ""\nmsgstr ""\n"Language: {lang}\\n"\n"Plural-Forms: {rule}\\n"\n\n')

    def entry(mid, mpl, forms):
        return (f'msgid "{mid}"\nmsgid_plural "{mpl}"\n'
                + "".join(f'msgstr[{i}] "{t}"\n' for i, t in enumerate(forms)) + "\n")
    return head + entry("One message", "%d messages", forms_msg) + entry("%d file", "%d files", forms_file)


def run(tmp_path, lang, body):
    (tmp_path / "en.po").write_text(SRC, encoding="utf-8")
    (tmp_path / f"{lang}.po").write_text(body, encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "kaeris", "check", "--source", str(tmp_path / "en.po"),
                        "--langs", lang], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
    return r.returncode, r.stdout + r.stderr


def test_slots_one_number_selects_are_found_from_the_formula():
    assert fm.single_number_slots(f"Plural-Forms: {AR}\n") == {0, 1, 2}
    assert fm.single_number_slots(f"Plural-Forms: {PL}\n") == {0}
    assert fm.single_number_slots(f"Plural-Forms: {CS}\n") == {0}
    assert fm.single_number_slots(f"Plural-Forms: {HE}\n") == {0, 1}
    assert fm.single_number_slots(f"Plural-Forms: {RU}\n") == set()
    assert fm.single_number_slots(f"Plural-Forms: {SL}\n") == set()
    assert fm.single_number_slots(f"Plural-Forms: {LV}\n") == set()
    assert fm.single_number_slots(f"Plural-Forms: {JA}\n") == set()


def test_loose_slots_need_a_valid_formula_that_is_the_languages_own():
    """Critic 21.11 (B2): the slots are read loosely only when the file's formula is sound
    (every value below nplurals) AND gives the same slot for every n as the formula of the
    file's Language in the server's gettext table (formats.PLURAL_RULES). Else: strict."""
    head = lambda lang, rule: (f"Language: {lang}\n" if lang else "") + f"Plural-Forms: {rule}\n"
    assert fm.po_loose_slots(head("ar", AR)) == {0, 1, 2}
    assert fm.po_loose_slots(head("pl", PL)) == {0}
    assert fm.po_loose_slots(head("he", HE)) == {0, 1}
    # full code first, then the base (pt-PT counts 0 as plural, Brazilian pt does not)
    assert fm.po_loose_slots(head("pt_PT", "nplurals=2; plural=(n != 1);")) == {0}
    assert fm.po_loose_slots(head("pt_BR", "nplurals=2; plural=(n != 1);")) == set()
    # the same rule spelled another way is the same rule
    assert fm.po_loose_slots(head("he", "nplurals=3; plural=n==1 ? 0 : (n==2 ? 1 : 2);")) == {0, 1}
    # no Language header: the language check was asked for
    assert fm.po_loose_slots(head("", AR), "ar") == {0, 1, 2}
    # broken: values past nplurals
    assert fm.po_loose_slots(head("ru", "nplurals=3; plural=n;")) == set()
    assert fm.po_loose_slots(head("he", "nplurals=2; plural=(n==1 ? 0 : n==2 ? 1 : 2);")) == set()
    assert fm.single_number_slots("Plural-Forms: nplurals=3; plural=n;\n") is None
    # sound, but another language's formula
    assert fm.po_loose_slots(head("ru", HE)) == set()
    assert fm.po_loose_slots(head("pl", CS)) == set()
    # a language the table does not know, or no language at all
    assert fm.po_loose_slots(head("xx", AR)) == set()
    assert fm.po_loose_slots(head("", AR)) == set()


def test_a_formula_that_does_not_parse_selects_nothing():
    assert fm.single_number_slots("Plural-Forms: nplurals=2; plural=(n != 1;\n") is None
    assert fm.single_number_slots("Plural-Forms: nplurals=2; plural=n ? import os : 1;\n") is None
    assert fm.single_number_slots("Language: de\n") is None


# name -> (lang, Plural-Forms, msgstr of "One message", msgstr of "%d file", check passes)
# (npm/test/gen_baselines.py replays the same cases against the npm port)
CASES = {
    "ar-zero-one-two-without-number": ("ar", AR,
        ["لا رسائل", "رسالة واحدة", "رسالتان", "%d رسائل", "%d رسالة", "%d رسالة"],
        ["لا ملفات", "ملف واحد", "ملفان", "%d ملفات", "%d ملفًا", "%d ملف"], True),
    "ar-many-without-number": ("ar", AR,
        ["لا رسائل", "رسالة واحدة", "رسالتان", "%d رسائل", "رسالة", "%d رسالة"],
        ["لا ملفات", "ملف واحد", "ملفان", "%d ملفات", "%d ملفًا", "%d ملف"], False),
    # Polish msgstr[1] covers 2-4, 22-24…: the number must stay.
    "pl-few-without-number": ("pl", PL, ["Jedna wiadomość", "wiadomości", "%d wiadomości"],
                              ["Jeden plik", "%d pliki", "%d plików"], False),
    "pl-one-without-number": ("pl", PL, ["Jedna wiadomość", "%d wiadomości", "%d wiadomości"],
                              ["Jeden plik", "%d pliki", "%d plików"], True),
    "he-two-without-number": ("he", HE, ["הודעה אחת", "שתי הודעות", "%d הודעות"],
                              ["קובץ אחד", "שני קבצים", "%d קבצים"], True),
    # Critic 21.11 (B2): the loose reading must not trust a formula the file got wrong.
    # `plural=n` gives every slot "one n" — a broken formula (values up to 1000 >= nplurals=3).
    "ru-formula-plural-n": ("ru", "nplurals=3; plural=n;",
                            ["%d сообщение", "%d сообщения", "%d сообщений"],
                            ["%d файл", "файла", "файлов"], False),
    # A valid formula, but Hebrew's in a Russian file: ru msgstr[1] is few (2-4, 22-24…).
    "ru-hebrew-formula": ("ru", HE, ["%d сообщение", "%d сообщения", "%d сообщений"],
                          ["%d файл", "файла", "%d файлов"], False),
    # Hebrew's own formula, but nplurals=2: the formula gives slot 2, which does not exist.
    "he-nplurals-below-values": ("he", "nplurals=2; plural=(n==1 ? 0 : n==2 ? 1 : 2);",
                                 ["הודעה אחת", "%d הודעות"], ["קובץ אחד", "שני קבצים"], False),
}


def files(name):
    lang, rule, msg, fil, _ok = CASES[name]
    return {"en.po": SRC, f"{lang}.po": target(lang, msg, fil, rule)}


@pytest.mark.parametrize("name", sorted(CASES))
def test_check_reads_single_number_slots_loosely_and_the_rest_strictly(tmp_path, name):
    lang, _rule, _msg, _fil, passes = CASES[name]
    code, out = run(tmp_path, lang, files(name)[f"{lang}.po"])
    if passes:
        assert code == 0, out
    else:
        assert code == 1 and "%d" in out, out
