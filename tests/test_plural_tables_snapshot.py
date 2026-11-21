"""The CLI's plural tables are the server's, held to a snapshot in this repository (critic round 2,
21.11: the py <-> server comparison ran only in the server's CI, which was not running).

tests/data/server_plural_tables.json is the server's backend/translator.py tables, written by
tests/data/refresh_server_plural_tables.py. Here, in the kaeris-cli CI on every push: the Python
copies must equal it (npm/test/plural-tables-snapshot.test.js holds the npm copies to the same
file). The other half, snapshot == server, runs wherever the backend is importable:
tests/test_detector_parity.py (the server's CI and the release machine) and the server's own
backend/tests/test_plural_tables_snapshot.py. No skip here: this file needs nothing but itself.
"""
import json
import os

from kaeris import detectors as det
from kaeris import formats as fm

SNAP = json.load(open(os.path.join(os.path.dirname(__file__), "data", "server_plural_tables.json"),
                      encoding="utf-8"))


def test_gettext_table_is_the_snapshot():
    """formats.PLURAL_RULES: what `check` trusts a .po Plural-Forms by (po_loose_slots)."""
    assert {k: [n, e] for k, (n, e) in fm.PLURAL_RULES.items()} == SNAP["PLURAL_RULES"]
    assert SNAP["PLURAL_DEFAULT"] == [2, "(n != 1)"]


def test_cldr_tables_are_the_snapshot():
    """detectors._CLDR_REQUIRED / _NO_SINGULAR / _HAS_ONE: the forms `check` asks of a target."""
    assert {k: sorted(v) for k, v in det._CLDR_REQUIRED.items()} == SNAP["CLDR_REQUIRED"]
    assert sorted(det._NO_SINGULAR) == SNAP["NO_SINGULAR"]
    assert sorted(det._HAS_ONE) == SNAP["HAS_ONE"]


def test_the_snapshot_is_whole():
    """A truncated or hand-edited snapshot would make the comparisons above vacuous."""
    rules = SNAP["PLURAL_RULES"]
    assert len(rules) >= 25 and rules["ar"][0] == 6 and rules["pl"][0] == 3, rules
    assert SNAP["CLDR_REQUIRED"]["pl"] == ["few", "many", "one"]
    assert "ja" in SNAP["NO_SINGULAR"] and "de" in SNAP["HAS_ONE"]


def test_the_snapshot_pins_the_po_slot_order():
    """_PO_SLOT_CATS: the order translate lays a target's .po slots out in (critic round 3: a
    reordered ro row passed every guard). The CLI has no copy of it; the snapshot pins it so the
    server's guard (backend/tests/test_plural_tables_snapshot.py, test_detector_parity) fails on
    any change until both files are refreshed. Each row has nplurals slots of distinct CLDR
    categories."""
    slots = SNAP["PO_SLOT_CATS"]
    assert slots["ar"] == ["zero", "one", "two", "few", "many", "other"], slots
    assert slots["lv"] == ["zero", "one", "other"] and slots["ro"] == ["one", "few", "other"], slots
    for lang, cats in slots.items():
        assert len(cats) == SNAP["PLURAL_RULES"][lang][0] and len(set(cats)) == len(cats), lang
        assert set(cats) <= {"zero", "one", "two", "few", "many", "other"}, lang
