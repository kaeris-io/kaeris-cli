"""P0.2.47 step 2 (21.11): once `translate` wrote every Arabic .po slot with its own form,
`kaeris check` failed our own output: msgstr[1] is read against msgid_plural, and Arabic's
msgstr[1] is the `one` slot — "رسالة واحدة" ("one message") is correct without the number.

gettext's `msgfmt -c` allows exactly this: a slot the Plural-Forms formula picks for ONE n only
may leave the number out (Arabic zero/one/two = 0/1/2, Polish one = 1). A slot that covers many
numbers must keep it. The formula is the target file's own, evaluated — no table.
"""
import os
import subprocess
import sys

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


def test_a_formula_that_does_not_parse_selects_nothing():
    assert fm.single_number_slots("Plural-Forms: nplurals=2; plural=(n != 1;\n") is None
    assert fm.single_number_slots("Plural-Forms: nplurals=2; plural=n ? import os : 1;\n") is None
    assert fm.single_number_slots("Language: de\n") is None


def test_arabic_zero_one_two_without_the_number_pass(tmp_path):
    msg = ["لا رسائل", "رسالة واحدة", "رسالتان", "%d رسائل", "%d رسالة", "%d رسالة"]
    fil = ["لا ملفات", "ملف واحد", "ملفان", "%d ملفات", "%d ملفًا", "%d ملف"]
    code, out = run(tmp_path, "ar", target("ar", msg, fil, AR))
    assert code == 0, out


def test_arabic_many_without_the_number_still_fails(tmp_path):
    msg = ["لا رسائل", "رسالة واحدة", "رسالتان", "%d رسائل", "رسالة", "%d رسالة"]
    fil = ["لا ملفات", "ملف واحد", "ملفان", "%d ملفات", "%d ملفًا", "%d ملف"]
    code, out = run(tmp_path, "ar", target("ar", msg, fil, AR))
    assert code == 1 and "%d" in out, out


def test_polish_few_without_the_number_still_fails(tmp_path):
    """Polish msgstr[1] covers 2-4, 22-24…: the number must stay."""
    msg = ["Jedna wiadomość", "wiadomości", "%d wiadomości"]
    fil = ["Jeden plik", "%d pliki", "%d plików"]
    code, out = run(tmp_path, "pl", target("pl", msg, fil, PL))
    assert code == 1 and "%d" in out, out


def test_polish_one_without_the_number_passes(tmp_path):
    msg = ["Jedna wiadomość", "%d wiadomości", "%d wiadomości"]
    fil = ["Jeden plik", "%d pliki", "%d plików"]
    code, out = run(tmp_path, "pl", target("pl", msg, fil, PL))
    assert code == 0, out


def test_hebrew_two_without_the_number_passes(tmp_path):
    msg = ["הודעה אחת", "שתי הודעות", "%d הודעות"]
    fil = ["קובץ אחד", "שני קבצים", "%d קבצים"]
    code, out = run(tmp_path, "he", target("he", msg, fil, HE))
    assert code == 0, out
