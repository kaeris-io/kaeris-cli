"""`kaeris review`: hand verify.json to a reviewer who has no account, take the answer back.

The /review page (kaeris.dev/review) opens a verify.json in the reviewer's browser and gives back
verify.reviewed.json, with each decision under `_reviewer`. Until this command the author had to
know that chain by heart. `kaeris review` prints what is waiting for a human (per language, per
status), where to send the file and what to run on return; `kaeris review --apply` reads the
reviewed file, says what the reviewer decided and writes it through the same code as `kaeris fix`.
Nothing here talks to a server or costs anything.
"""
import copy
import io
import json
import unittest.mock as mock

import pytest

from kaeris import cli as K

DE = {"save": "Speichern Änderungen", "greet": "Willkommen zurück", "nav": {"contact": "Kontakt"}}


def _entry(src, tr, status="error", **kw):
    return {"status": status, "source": src, "translation": tr, **kw}


REVIEW = {"de": {
    "save": _entry("Save changes", "Speichern Änderungen", fix="Änderungen speichern"),
    "greet": _entry("Welcome back, {name}", "Willkommen zurück", status="review"),
    "nav.contact": _entry("Contact", "Kontakt", status="unchecked"),
}}


def _body(review=None):
    return {"de": {"save": "Save changes"}, "_review": copy.deepcopy(review or REVIEW), "_files": {"de": "de.json"},
            "_summary": {"lines": 9, "to_review": 3, "error": 1, "review": 1, "unchecked": 1}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "de.json").write_text(json.dumps(DE, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (tmp_path / "verify.json").write_text(json.dumps(_body(), ensure_ascii=False, indent=2), "utf-8")
    monkeypatch.setattr(K, "_client", lambda a: (_ for _ in ()).throw(AssertionError("network")))
    return tmp_path


def _main(*argv):
    err, out = io.StringIO(), io.StringIO()
    with mock.patch("sys.stderr", err), mock.patch("sys.stdout", out):
        code = K.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _reviewed(project, decisions, review=None):
    """What /review writes back: kept lines leave `_review`, the decision goes to `_reviewer`."""
    body = _body(review)
    body["_reviewer"] = {"de": decisions}
    for key, d in decisions.items():
        if d["decision"] == "keep":
            del body["_review"]["de"][key]
        elif d["decision"] == "own":
            body["_review"]["de"][key]["fix"] = d["text"]
    (project / "verify.reviewed.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), "utf-8")


def test_review_counts_lines_per_language_and_status(project):
    code, out, err = _main("review", "--json")
    assert code == 0, err
    rep = json.loads(out)
    assert rep["verify"] == "verify.json"
    assert rep["to_review"] == 3
    assert rep["by_lang"] == {"de": {"error": 1, "review": 1, "unchecked": 1}}
    assert rep["url"] == "https://kaeris.dev/review"


def test_review_says_where_to_send_the_file_and_what_to_run_back(project):
    code, _out, err = _main("review")
    assert code == 0, err
    assert "kaeris.dev/review" in err
    assert "verify.json" in err
    assert "kaeris review --apply" in err
    assert "no account" in err.lower()


def test_review_without_a_verify_file_is_one_clear_error(project):
    (project / "verify.json").unlink()
    code, _out, err = _main("review")
    assert code == 2
    assert "verify" in err and "--verify" in err


def test_review_of_a_clean_run_has_nothing_to_send(project):
    (project / "verify.json").write_text(json.dumps(_body({"de": {}})), "utf-8")
    code, _out, err = _main("review")
    assert code == 0
    assert "nothing to review" in err.lower()


def test_review_warns_when_fixes_were_already_applied(project):
    body = _body()
    body["_applied"] = [{"lang": "de", "key": "save", "how": "fix", "why": "suggested fix"}]
    (project / "verify.json").write_text(json.dumps(body), "utf-8")
    code, _out, err = _main("review")
    assert code == 0
    assert "already applied" in err.lower()


def test_review_open_launches_the_page_and_only_that(project):
    with mock.patch("webbrowser.open") as opened:
        code, _out, err = _main("review", "--open")
    assert code == 0, err
    opened.assert_called_once_with("https://kaeris.dev/review")


def test_review_never_opens_a_browser_unasked(project):
    with mock.patch("webbrowser.open") as opened:
        _main("review")
    opened.assert_not_called()


def test_apply_reports_decisions_and_writes_the_chosen_lines(project):
    _reviewed(project, {
        "save": {"decision": "fix"},
        "greet": {"decision": "own", "text": "Willkommen zurück, {name}!"},
        "nav.contact": {"decision": "keep"},
    })
    code, _out, err = _main("review", "--apply")
    assert code == 0, err
    assert "3 of 3 decided" in err
    assert "1 kept" in err and "1 suggested" in err and "1 own" in err
    de = json.loads((project / "de.json").read_text("utf-8"))
    assert de["save"] == "Änderungen speichern"
    assert de["greet"] == "Willkommen zurück, {name}!"
    assert de["nav"]["contact"] == "Kontakt"


def test_apply_says_how_many_lines_nobody_decided_and_leaves_them(project):
    _reviewed(project, {"save": {"decision": "fix"}})
    code, _out, err = _main("review", "--apply")
    assert code == 0, err
    assert "1 of 3 decided" in err
    assert "2 not decided" in err
    de = json.loads((project / "de.json").read_text("utf-8"))
    assert de["greet"] == "Willkommen zurück"


def test_apply_dry_run_writes_nothing(project):
    _reviewed(project, {"save": {"decision": "fix"}})
    before = (project / "de.json").read_bytes()
    code, _out, err = _main("review", "--apply", "--dry-run")
    assert code == 0, err
    assert (project / "de.json").read_bytes() == before


def test_apply_without_the_reviewed_file_says_what_is_missing(project):
    code, _out, err = _main("review", "--apply")
    assert code == 2
    assert "verify.reviewed.json" in err


def test_apply_takes_an_explicit_path(project):
    _reviewed(project, {"save": {"decision": "fix"}})
    (project / "verify.reviewed.json").rename(project / "from-anna.json")
    code, _out, err = _main("review", "--apply", "from-anna.json")
    assert code == 0, err
    assert json.loads((project / "de.json").read_text("utf-8"))["save"] == "Änderungen speichern"


def test_review_json_with_apply_carries_decisions_and_the_fix_result(project):
    _reviewed(project, {"save": {"decision": "fix"}, "nav.contact": {"decision": "keep"}})
    code, out, err = _main("review", "--apply", "--json")
    assert code == 0, err
    rep = json.loads(out)
    assert rep["decisions"] == {"fix": 1, "own": 0, "keep": 1, "undecided": 1}
    assert rep["counts"]["applied"] == 1
