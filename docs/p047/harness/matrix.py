"""translate -> check matrix on a LOCAL server with a stub model ($0, no real keys).

usage: python matrix.py <tag> <cli-worktree> <i18n_tool-worktree> [py|npm|both] [case,case]

Starts stub_model.py and the backend (uvicorn) as child processes, runs every case in a fresh
folder, writes <tag>.txt next to this script, and stops both children by their own PIDs.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
TAG, CLI, SRV = sys.argv[1], sys.argv[2], sys.argv[3]
WHICH = sys.argv[4] if len(sys.argv) > 4 else "both"
ONLY = set(sys.argv[5].split(",")) if len(sys.argv) > 5 else None
# cy (Welsh) is not one of the 46 languages the server translates: it is tried once below and
# refused before anything is sent.
LANGS = ["pl", "ru", "ar", "ja"]
STUB_PORT, API_PORT = 18990, 18991
VENV_PY = r"C:\Users\Inzagi\projects\kaeris\i18n_tool\.venv\Scripts\python.exe"

XC = {"sourceLanguage": "en", "version": "1.0", "strings": {"%lld files": {"localizations": {"en": {
    "variations": {"plural": {"one": {"stringUnit": {"state": "translated", "value": "%lld file"}},
                              "other": {"stringUnit": {"state": "translated", "value": "%lld files"}}}}}}}}}

CASES = {
    "i18next": ("en.json", json.dumps({"items_one": "{{count}} item", "items_other": "{{count}} items",
                                       "title": "Inbox"})),
    "i18next-nested-ns": ("en.json", json.dumps({"cart": {"items_one": "{{count}} item in the cart",
                                                          "items_other": "{{count}} items in the cart"}})),
    "nested": ("en.json", json.dumps({"items": {"one": "{{count}} item", "other": "{{count}} items"},
                                      "title": "Inbox"})),
    "icu": ("en.json", json.dumps({"files": "{n, plural, one {# file} other {# files}}"})),
    "ordinal": ("en.json", json.dumps({"place_ordinal_one": "{{count}}st place",
                                       "place_ordinal_two": "{{count}}nd place",
                                       "place_ordinal_few": "{{count}}rd place",
                                       "place_ordinal_other": "{{count}}th place"})),
    "yaml": ("en.yml", 'en:\n  items:\n    one: "%{count} item"\n    other: "%{count} items"\n  title: Inbox\n'),
    "po": ("en.po", 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
                    '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'
                    'msgid "%d file"\nmsgid_plural "%d files"\nmsgstr[0] "%d file"\nmsgstr[1] "%d files"\n'),
    # POT-style (empty msgstr), msgctxt twins, a singular without the number, %s count.
    "po-multi": ("en.po", 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
                          '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n"Language: en\\n"\n\n'
                          'msgid "Inbox"\nmsgstr ""\n\n'
                          'msgctxt "mail"\nmsgid "One message"\nmsgid_plural "%d messages"\n'
                          'msgstr[0] ""\nmsgstr[1] ""\n\n'
                          'msgctxt "chat"\nmsgid "One message"\nmsgid_plural "%d messages"\n'
                          'msgstr[0] ""\nmsgstr[1] ""\n\n'
                          'msgid "%s file deleted"\nmsgid_plural "%s files deleted"\n'
                          'msgstr[0] ""\nmsgstr[1] ""\n'),
    "arb": ("app_en.arb", json.dumps({"@@locale": "en",
                                      "files": "{count, plural, one {{count} file} other {{count} files}}",
                                      "@files": {"placeholders": {"count": {"type": "int"}}}})),
    "xcstrings": ("Localizable.xcstrings", json.dumps(XC)),
    "android": ("values/strings.xml", '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                '  <plurals name="files">\n    <item quantity="one">%d file</item>\n'
                '    <item quantity="other">%d files</item>\n  </plurals>\n</resources>\n'),
    "ftl": ("en.ftl", "emails =\n    { $count ->\n        [one] { $count } email\n"
                      "       *[other] { $count } emails\n    }\n"),
}
# --only-new (Python only): first run writes the files and the lock, the second run must keep
# them; an old one/other-only target (what 0.2.46 wrote) must be completed.
INCREMENTAL = {"i18next", "nested", "i18next-nested-ns"}


def wait_up(url, secs=60):
    end = time.time() + secs
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return True
        except Exception as e:
            if hasattr(e, "code"):
                return True
            time.sleep(0.5)
    return False


def run(cmd, cwd, env):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    # run_cli.py's "using <tree>/kaeris/__init__.py" line: the header names it once per run
    err = "\n".join(l for l in p.stderr.splitlines() if not l.startswith("using "))
    return p.returncode, (p.stdout + ("\n[stderr] " + err if err.strip() else "")).strip()


def plural_lines(text):
    return [l.strip() for l in text.splitlines() if "plural" in l.lower() or "missing" in l.lower()
            or "extra" in l.lower() or "stale" in l.lower()]


def main():
    out_lines = []
    say = lambda s="": (out_lines.append(s), print(s, flush=True))
    # P047_RUNS / P047_OUT: where the run folders and <tag>.txt go (default: next to this script)
    work = os.path.join(os.environ.get("P047_RUNS") or os.path.join(HERE, "runs"), TAG)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    srv_env = dict(os.environ, PYTHONUTF8="1", OPENROUTER_API_KEY="ci-not-a-real-key",
                   OPENROUTER_URL=f"http://127.0.0.1:{STUB_PORT}/api/v1/chat/completions",
                   AUTO_TERMS="0", MAX_RETRIES="1", KAERIS_DATA_DIR=os.path.join(work, "_srvdata"))
    stub = subprocess.Popen([VENV_PY, os.path.join(HERE, "stub_model.py"), str(STUB_PORT)])
    api = subprocess.Popen([VENV_PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                            "--port", str(API_PORT), "--log-level", "warning"],
                           cwd=os.path.join(SRV, "backend"), env=srv_env,
                           stdout=open(os.path.join(work, "_server.log"), "w"), stderr=subprocess.STDOUT)
    say(f"# {TAG}: stub pid {stub.pid}, api pid {api.pid}")
    say(f"# cli {CLI} @ {git(CLI)}; server {SRV} @ {git(SRV)}")
    try:
        if not wait_up(f"http://127.0.0.1:{API_PORT}/api/languages"):
            say("API did not come up"); return 2
        cli_env = dict(os.environ, PYTHONUTF8="1", CI="1",
                       KAERIS_API_URL=f"http://127.0.0.1:{API_PORT}", PYTHONPATH=CLI)
        cli_env.pop("KAERIS_API_KEY", None)
        runner = os.path.join(HERE, "run_cli.py")      # the tree's kaeris, not an installed one
        say("# kaeris run from: " + subprocess.run(
            [sys.executable, runner, CLI, "--which"], cwd=work,
            env=cli_env, capture_output=True, text=True).stderr.strip())
        tools = {"py": [sys.executable, runner, CLI],
                 "npm": ["node", os.path.join(CLI, "npm", "bin", "kaeris.js")]}
        summary = []
        d = os.path.join(work, "cy-probe")
        os.makedirs(d)
        with open(os.path.join(d, "en.json"), "w", encoding="utf-8") as f:
            f.write(CASES["i18next"][1])
        code, txt = run(tools["py"] + ["translate", "en.json", "--langs", "cy"], d, cli_env)
        say(f"$ kaeris translate en.json --langs cy -> exit {code}\n  | " + txt.splitlines()[-1])
        for tool in (["py", "npm"] if WHICH == "both" else [WHICH]):
            for case, (name, body) in CASES.items():
                if ONLY and case not in ONLY:
                    continue
                d = os.path.join(work, f"{tool}-{case}")
                src = os.path.join(d, name)
                os.makedirs(os.path.dirname(src), exist_ok=True)
                with open(src, "w", encoding="utf-8", newline="\n") as f:
                    f.write(body)
                rel = name.replace("/", os.sep)
                say(f"\n=== [{tool}] {case}: {name}")
                code, txt = run(tools[tool] + ["translate", rel, "--langs", ",".join(LANGS),
                                               "--no-only-new"], d, cli_env)
                say(f"$ kaeris translate {name} --langs {','.join(LANGS)}  -> exit {code}")
                if code != 0:
                    say("  | " + "\n  | ".join(txt.splitlines()[-12:]))
                for lang in LANGS:
                    code, txt = run(tools[tool] + ["check", "--source", rel, "--langs", lang], d, cli_env)
                    pl = plural_lines(txt)
                    verdict = "GREEN" if code == 0 and not pl else ("WARN" if code == 0 else "RED")
                    summary.append((tool, case, lang, code, verdict))
                    say(f"$ kaeris check --source {name} --langs {lang}  -> exit {code}  {verdict}")
                    for l in (pl or txt.splitlines()[-2:]):
                        say(f"  | {l}")
                if tool == "py" and case in INCREMENTAL and os.path.isfile(os.path.join(d, "pl.json")):
                    incremental(tools[tool], d, rel, cli_env, say, summary, case)
                if case.startswith("po"):
                    po_slots(d, tool, case, say, summary)
                    if tool == "py":
                        po_only_new(tools[tool], d, rel, cli_env, say, summary, case)
            say("")
        say("\n# SUMMARY tool case lang exit verdict")
        for row in summary:
            say("  " + " ".join(str(x) for x in row))
        bad = [r for r in summary if r[4] != "GREEN"]
        say(f"# {len(summary) - len(bad)}/{len(summary)} GREEN")
        dump_outputs(work, say)
    finally:
        for p in (api, stub):
            p.terminate()
            try:
                p.wait(10)
            except Exception:
                p.kill()
        say(f"# stopped pids {api.pid} {stub.pid}: api rc={api.poll()} stub rc={stub.poll()}")
        with open(os.path.join(os.environ.get("P047_OUT") or HERE, f"{TAG}.txt"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")


def incremental(tool, d, rel, env, say, summary, case):
    """--only-new on a folder whose pl/ru targets hold only one/other (0.2.46 output)."""
    src = json.load(open(os.path.join(d, rel), encoding="utf-8"))
    old = {}
    for lang in ("pl", "ru"):
        p = os.path.join(d, f"{lang}.json")
        tgt = json.load(open(p, encoding="utf-8"))
        flat_keep = trim(tgt, src)
        json.dump(flat_keep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        old[lang] = flat_keep
    for f in ("kaeris.lock",):
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    for step in ("first", "second"):
        code, txt = run(tool + ["translate", rel, "--langs", "pl,ru", "--only-new", "--assume-current"]
                        if step == "first" else tool + ["translate", rel, "--langs", "pl,ru", "--only-new"],
                        d, env)
        say(f"$ kaeris translate {rel} --langs pl,ru --only-new{' --assume-current' if step == 'first' else ''}"
            f"  ({step}, targets trimmed to the source's own forms) -> exit {code}")
        say("  | " + "\n  | ".join(l for l in txt.splitlines() if "pl:" in l or "ru:" in l or "✗" in l)[:1500])
        for lang in ("pl", "ru"):
            code, txt = run(tool + ["check", "--source", rel, "--langs", lang], d, env)
            pl = plural_lines(txt)
            verdict = "GREEN" if code == 0 and not pl else ("WARN" if code == 0 else "RED")
            summary.append(("py", f"{case}+only-new-{step}", lang, code, verdict))
            say(f"$ kaeris check --source {rel} --langs {lang}  -> exit {code}  {verdict}")
            for l in (pl or txt.splitlines()[-2:]):
                say(f"  | {l}")
        say("  pl.json: " + open(os.path.join(d, "pl.json"), encoding="utf-8").read().replace("\n", " "))


# Where the stub's `one` form (the singular, no category suffix) must land in each target's
# msgstr[] order. The stub gives every other category its own word, so a copied slot shows.
ONE_SLOT = {"pl": 0, "ru": 0, "ar": 1}


def parse_po(path):
    """[(entry, header_nplurals)] — entry: {msgctxt?, msgid, msgid_plural?, strs: {i: text}}."""
    import re
    text = open(path, encoding="utf-8").read()
    m = re.search(r"Plural-Forms: nplurals=(\d+)", text)
    entries, cur = [], None
    for line in text.splitlines():
        r = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?) "(.*)"$', line.strip())
        if not r:
            continue
        kw = r.group(1)
        if kw == "msgctxt" or (kw == "msgid" and (cur is None or "msgid" in cur)):
            cur = {"strs": {}}
            entries.append(cur)
        if kw.startswith("msgstr"):
            cur["strs"][int(r.group(2) or 0)] = r.group(3)
        else:
            cur[kw] = r.group(3)
    return [e for e in entries if e.get("msgid")], int(m.group(1)) if m else None


def po_slots(d, tool, case, say, summary):
    """Every plural entry of every target: as many msgstr as the header's nplurals, each slot
    its own form, the singular in the `one` slot, and Japanese's one slot = the plural form."""
    sys.path.insert(0, HERE)
    import stub_model
    for lang in LANGS:
        p = os.path.join(d, f"{lang}.po")
        if not os.path.isfile(p):
            summary.append((tool, f"{case}-slots", lang, "-", "RED"))
            say(f"  [{lang}] no {lang}.po")
            continue
        entries, n = parse_po(p)
        faults = []
        for e in entries:
            if "msgid_plural" not in e:
                continue
            strs = [e["strs"].get(i) for i in range(len(e["strs"]))]
            tag = f"{e.get('msgctxt', '')}|{e['msgid']}"
            if len(strs) != n:
                faults.append(f"{tag}: {len(strs)} msgstr, header nplurals={n}")
            if n and n > 1 and len(set(strs)) != len(strs):
                faults.append(f"{tag}: slots repeat a form {strs}")
            if lang in ONE_SLOT and len(strs) > ONE_SLOT[lang] and \
                    strs[ONE_SLOT[lang]] != stub_model.plain(e["msgid"], lang):
                faults.append(f"{tag}: msgstr[{ONE_SLOT[lang]}] is not the singular {strs}")
            if n == 1 and strs and strs[0] != stub_model.plain(e["msgid_plural"], lang):
                faults.append(f"{tag}: msgstr[0] is not the plural form {strs}")
        verdict = "GREEN" if not faults else "RED"
        summary.append((tool, f"{case}-slots", lang, "-", verdict))
        say(f"  [{lang}] po slots nplurals={n}: {verdict}" + "".join(f"\n  |   {f}" for f in faults))


def po_only_new(tool, d, rel, env, say, summary, case):
    """--only-new on .po: the CLI translates the whole file (JSON/ARB only), and the result
    must be the same file — no slot lost, none added."""
    read = lambda: {l: open(os.path.join(d, f"{l}.po"), encoding="utf-8").read()
                    for l in LANGS if os.path.isfile(os.path.join(d, f"{l}.po"))}
    before = read()
    code, txt = run(tool + ["translate", rel, "--langs", ",".join(LANGS), "--only-new"], d, env)
    same = read() == before and len(before) == len(LANGS)
    verdict = "GREEN" if code == 0 and same else "RED"
    summary.append(("py", f"{case}+only-new", ",".join(LANGS), code, verdict))
    say(f"$ kaeris translate {rel} --langs {','.join(LANGS)} --only-new  -> exit {code}  "
        f"files identical to the full run: {same}  {verdict}")
    say("  | " + "\n  | ".join(l for l in txt.splitlines() if "only-new" in l or "memory" in l.lower()))
    po_slots(d, "py", case + "+only-new", say, summary)


def trim(tgt, src):
    """Keep only the keys the source has (what 0.2.46 delivered for an i18next/nested plural)."""
    if isinstance(src, dict) and isinstance(tgt, dict):
        return {k: trim(tgt[k], v) for k, v in src.items() if k in tgt}
    return tgt


def dump_outputs(work, say):
    say("\n# OUTPUT FILES (py)")
    for case in CASES:
        d = os.path.join(work, f"py-{case}")
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in sorted(files):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, d)
                if fn.startswith(("kaeris", "en.", "app_en")) or rel.startswith("values" + os.sep) \
                        or fn.endswith(".lock"):
                    continue
                if any(f"{l}." in fn or f"_{l}." in fn or f"values-{l}" in rel for l in ("pl", "ar", "ja")) \
                        or fn.endswith(".xcstrings"):
                    body = open(p, encoding="utf-8").read()
                    say(f"--- {case}/{rel}\n{body[:1200]}")


def git(path):
    try:
        return subprocess.run(["git", "-C", path, "log", "-1", "--format=%h %s"], capture_output=True,
                              text=True).stdout.strip()[:90]
    except Exception:
        return "?"


if __name__ == "__main__":
    sys.exit(main() or 0)
