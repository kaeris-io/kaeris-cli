"""Write the server's plural tables as JSON: the snapshot `kaeris check` (py and npm) is held to.

    python tests/data/refresh_server_plural_tables.py <i18n_tool/backend> [out.json]

Default out: tests/data/server_plural_tables.json next to this script. The same file sits in the
server repository (backend/tests/data/plural_tables.json) and both are compared:
  - tests/test_plural_tables_snapshot.py and npm/test/plural-tables-snapshot.test.js: the CLI's
    own copies (kaeris/formats.py, kaeris/detectors.py, npm/src/*.js) against this snapshot, in
    the kaeris-cli CI on every push;
  - tests/test_detector_parity.py (in the server's CI, KAERIS_BACKEND) and the server's
    backend/tests/test_plural_tables_snapshot.py: the server's tables against it.
A change to a server table therefore needs this script run and both copies committed.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def tables(translator) -> dict:
    return {
        "about": "backend/translator.py plural tables (_PLURAL_RULES, _PLURAL_DEFAULT, "
                 "_CLDR_REQUIRED, _NO_SINGULAR, _HAS_ONE, _PO_SLOT_CATS); written by "
                 "kaeris-cli tests/data/refresh_server_plural_tables.py",
        "PLURAL_RULES": {k: [n, e] for k, (n, e) in sorted(translator._PLURAL_RULES.items())},
        "PLURAL_DEFAULT": list(translator._PLURAL_DEFAULT),
        "CLDR_REQUIRED": {k: sorted(v) for k, v in sorted(translator._CLDR_REQUIRED.items())},
        "NO_SINGULAR": sorted(translator._NO_SINGULAR),
        "HAS_ONE": sorted(translator._HAS_ONE),
        # the order translate lays a target's .po slots out in (critic round 3: a reordered ro
        # row passed every guard); the CLI has no copy, the snapshot pins it for the server
        "PO_SLOT_CATS": {k: list(v) for k, v in sorted(translator._PO_SLOT_CATS.items())},
    }


def main():
    backend = os.path.abspath(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "server_plural_tables.json")
    sys.path.insert(0, backend)
    os.environ.setdefault("OPENROUTER_API_KEY", "ci-not-a-real-key")
    import translator
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tables(translator), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
