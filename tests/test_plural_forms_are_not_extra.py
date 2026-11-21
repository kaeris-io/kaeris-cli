"""check.plural_set_faults: the public reading kaeris-mcp uses after diff_locale (0.2.47, critic
round 2). A Polish `items_few` that translate now writes is a form the file owes, not an extra key;
a key the source never had still is."""
from kaeris import check as chk

SRC = {"items_one": "{{count}} item", "items_other": "{{count}} items", "title": "Inbox"}
PL = {"items_one": "{{count}} element", "items_few": "{{count}} elementy",
      "items_many": "{{count}} elementów", "items_other": "{{count}} elementu",
      "title": "Skrzynka", "old": "x"}


def test_owed_forms_are_not_extra():
    missing, extra, _ = chk.diff_locale(SRC, PL)
    assert extra == ["items_few", "items_many", "old"]
    faults, missing, extra = chk.plural_set_faults(SRC, PL, missing, extra, "pl")
    assert (faults, missing, extra) == ([], [], ["old"])


def test_it_is_the_reading_check_uses():
    assert chk.check_locales(SRC, ["pl"], lambda _l: PL, [])["extra"] == {"pl": ["old"]}
