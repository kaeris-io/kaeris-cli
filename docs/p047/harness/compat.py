"""Critic round 1 (21.11) cases on LOCAL servers with the stub model ($0, no real keys).

usage: python compat.py <out.txt> <runs-dir> CLI_NEW CLI_CAND CLI_046 CLI_045 SRV_NEW SRV_CAND SRV_PROD

  CLI_NEW  kaeris-cli plural-translate-1121 (0.2.47)   SRV_NEW  i18n_tool plural-translate-1121
  CLI_CAND e721b68 (round-1 candidate)                 SRV_CAND 88ee3052 (round-1 candidate)
  CLI_046  d5535f0 (0.2.46)  CLI_045 0.2.45            SRV_PROD 94114a89 (production)

Starts four stubs (normal, plain, noother, short) and six uvicorns (new, cand, prod, and new on
each broken stub), runs every case in a fresh folder under <runs-dir>, writes the log to
<out.txt>, and stops every child by its own PID. Python CLIs run from their tree (PYTHONPATH;
each one's kaeris.__file__ is printed), npm from <cli>/npm/bin/kaeris.js.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT, RUNS = sys.argv[1], sys.argv[2]
CLI = dict(zip(("new", "cand", "046", "045"), sys.argv[3:7]))
SRV = dict(zip(("new", "cand", "prod"), sys.argv[7:10]))
VENV_PY = r"C:\Users\Inzagi\projects\kaeris\i18n_tool\.venv\Scripts\python.exe"
STUBS = {"normal": 18960, "plain": 18961, "noother": 18962, "short": 18963}
SERVERS = {"new": ("new", "normal", 18964), "cand": ("cand", "normal", 18965),
           "prod": ("prod", "normal", 18966), "new-plain": ("new", "plain", 18967),
           "new-noother": ("new", "noother", 18968), "new-short": ("new", "short", 18969)}
LOG, ROWS = [], []


def say(s=""):
    LOG.append(s)
    print(s, flush=True)


def row(case, what, verdict, detail=""):
    ROWS.append((case, what, verdict, detail))
    say(f"  => [{verdict}] {case}: {what}" + (f" ({detail})" if detail else ""))


def wait_up(url, secs=90):
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


def cli_env(cli, server):
    env = dict(os.environ, PYTHONUTF8="1", CI="1", NO_COLOR="1", PYTHONPATH=CLI[cli],
               PYTHONDONTWRITEBYTECODE="1",
               KAERIS_API_URL=f"http://127.0.0.1:{SERVERS[server][2]}")
    env.pop("KAERIS_API_KEY", None)
    return env


def run(cli, server, args, cwd, tool="py", show=True):
    cmd = ([sys.executable, "-m", "kaeris"] if tool == "py"
           else ["node", os.path.join(CLI[cli], "npm", "bin", "kaeris.js")]) + args
    p = subprocess.run(cmd, cwd=cwd, env=cli_env(cli, server), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (p.stdout + ("\n[stderr] " + p.stderr if p.stderr.strip() else "")).strip()
    if show:
        say(f"$ [{tool} {cli} -> {server}] kaeris {' '.join(args)}  -> exit {p.returncode}")
        for l in out.splitlines():
            say("  | " + l)
    return p.returncode, out


def write(d, name, body):
    p = os.path.join(d, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2))


def read(d, name):
    p = os.path.join(d, name)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else None


def fresh(name):
    d = os.path.join(RUNS, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def stub_calls(mode="normal"):
    p = os.path.join(RUNS, f"_stub-{mode}.jsonl")
    return sum(1 for _ in open(p, encoding="utf-8")) if os.path.isfile(p) else 0


MIXED = {"msg_one": "One message from {{name}}", "msg_other": "{{count}} messages from {{name}}",
         "tag_one": "Item #{{count}}", "tag_other": "Items #{{count}}",
         "day": {"one": "One day", "other": "{{count}} days"}, "title": "Inbox"}
PO_EDGE = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
           '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n"Language: en\\n"\n\n'
           '#, c-format\nmsgid "Don\'t delete %d file"\nmsgid_plural "Don\'t delete %d files"\n'
           'msgstr[0] ""\nmsgstr[1] ""\n\n'
           '#, c-format\nmsgid "One message"\nmsgid_plural "%d messages"\nmsgstr[0] ""\nmsgstr[1] ""\n')
PO_SRC = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
          '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n"Language: en\\n"\n\n'
          'msgid "Open file"\nmsgstr ""\n\nmsgid "%d file"\nmsgid_plural "%d files"\nmsgstr[0] ""\n'
          'msgstr[1] ""\n')
ONLYNEW_SRC = {"cart": {"items_one": "{{count}} item in the cart",
                        "items_other": "{{count}} items in the cart", "title": "Cart"},
               "files": {"one": "{{count}} file", "other": "{{count}} files"}}


def same_file(d1, d2, name):
    a, b = read(d1, name), read(d2, name)
    return a is not None and a == b


def root_dotted(path):
    if not os.path.isfile(path):
        return ["<no file>"]
    obj = json.load(open(path, encoding="utf-8"))
    return [k for k in obj if "." in k]


# ── B1: one-form languages ──────────────────────────────────────────────────────────────────

def case_b1():
    say("\n######## B1: ja/zh/ko, a set whose singular has no number (critic: invented {{count}})")
    langs = ["ja", "zh", "ko"]
    dirs = {}
    for tag, cli, srv, tool in (("before", "cand", "cand", "py"), ("after", "new", "new", "py"),
                                ("after-npm", "new", "new", "npm"), ("prod", "046", "prod", "py")):
        d = dirs[tag] = fresh(f"b1-{tag}")
        write(d, "en.json", MIXED)
        say(f"\n=== B1 {tag}: translate with {tool} {cli} on server {srv}")
        run(cli, srv, ["translate", "en.json", "--langs", ",".join(langs), "--no-only-new"]
            + (["--no-tm"] if tool == "py" else []), d, tool)   # npm has no project memory
        for lang in langs:
            say(f"--- {tag}/{lang}.json\n{read(d, lang + '.json')}")
        codes = {}
        for chk_cli, chk_tool in (("new", "py"), ("new", "npm"), ("046", "py"), ("045", "py")):
            for lang in langs:
                code, _ = run(chk_cli, srv, ["check", "--source", "en.json", "--langs", lang], d,
                              chk_tool)
                codes[(chk_cli, chk_tool, lang)] = code
        summary = " ".join(f"{c}/{t}/{l}={v}" for (c, t, l), v in codes.items())
        if tag == "before":
            row("B1", f"{tag} (cli e721b68 + server 88ee3052): check exits", "info", summary)
        elif tag != "prod":
            row("B1", f"{tag}: check 0.2.47 py/npm, 0.2.46, 0.2.45 on ja/zh/ko all exit 0",
                "GREEN" if not any(codes.values()) else "RED", summary)
    for lang in langs:
        same = same_file(dirs["after"], dirs["prod"], f"{lang}.json")
        row("B1", f"{lang}.json after (0.2.47 + new server) == 0.2.46 + production server",
            "GREEN" if same else "RED")


# ── B2: what the loose .po reading must not let through ─────────────────────────────────────

def case_b2():
    say("\n######## B2: Plural-Forms the loose reading must not trust")
    ru_head = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
               '"Plural-Forms: {pf}\\n"\n"Language: ru\\n"\n\n#, c-format\n'
               'msgid "%d file"\nmsgid_plural "%d files"\n')
    en = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
          '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n"Language: en\\n"\n\n#, c-format\n'
          'msgid "%d file"\nmsgid_plural "%d files"\nmsgstr[0] ""\nmsgstr[1] ""\n')
    cases = {"plural=n": (ru_head.format(pf="nplurals=3; plural=n;")
                          + 'msgstr[0] "%d файл"\nmsgstr[1] "файла"\nmsgstr[2] "файлов"\n'),
             "hebrew-formula-in-ru": (ru_head.format(pf="nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);")
                                      + 'msgstr[0] "%d файл"\nmsgstr[1] "файла"\nmsgstr[2] "%d файлов"\n')}
    for name, body in cases.items():
        d = fresh(f"b2-{name}")
        write(d, "en.po", en)
        write(d, "ru.po", body)
        say(f"\n=== B2 {name}")
        got = {}
        for cli, tool in (("cand", "py"), ("new", "py"), ("new", "npm"), ("046", "py")):
            got[(cli, tool)], _ = run(cli, "new", ["check", "--source", "en.po", "--langs", "ru"], d, tool)
        row("B2", f"{name}: check 0.2.47 py and npm exit 1 (strict, as 0.2.46)",
            "GREEN" if got[("new", "py")] == 1 and got[("new", "npm")] == 1 else "RED",
            " ".join(f"{c}/{t}={v}" for (c, t), v in got.items()))
    say("\n=== B2 every case of tests/test_po_single_number_slots.py against msgfmt -c")
    p = subprocess.run([sys.executable, os.path.join(HERE, "b2_msgfmt.py"), CLI["new"]],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for l in p.stdout.splitlines():
        say("  | " + l)
    bad = []
    for l in p.stdout.splitlines()[2:]:
        name, expect, py, npm = (l.split() + ["", "", "", ""])[:4]
        want = "0" if expect == "pass" else "1"
        if not (py == want and npm == want):
            bad.append(l)
    row("B2", "slot cases: py and npm agree with the expected verdict", "GREEN" if not bad else "RED",
        "; ".join(bad))


# ── old CLI (0.2.46) on the new server: what production gives ──────────────────────────────

def onlynew(cli, srv, tag, tool="py"):
    d = fresh(f"onlynew-{tag}")
    src = json.loads(json.dumps(ONLYNEW_SRC))
    write(d, "en.json", src)
    say(f"\n=== only-new {tag}: {tool} {cli} on {srv}")
    run(cli, srv, ["translate", "en.json", "--langs", "pl,de", "--no-only-new"], d, tool)
    src["cart"]["saved_one"] = "{{count}} saved item"
    src["cart"]["saved_other"] = "{{count}} saved items"
    src["files"]["other"] = "{{count}} files total"
    src["new_title"] = "Wishlist"
    write(d, "en.json", src)
    outs = []
    for i in range(3):
        before = stub_calls()
        code, out = run(cli, srv, ["translate", "en.json", "--langs", "pl,de", "--only-new"], d, tool)
        outs.append((code, out, stub_calls() - before))
    say(f"--- {tag}/pl.json\n{read(d, 'pl.json')}")
    checks = {lang: run(cli, srv, ["check", "--source", "en.json", "--langs", lang], d, tool)[0]
              for lang in ("pl", "de")}
    return d, outs, checks


def case_old_cli_new_server():
    say("\n######## old CLI 0.2.46 + new server = what the production server gives")
    d_new, outs_new, _ = onlynew("046", "new", "046-on-new")
    d_prod, outs_prod, _ = onlynew("046", "prod", "046-on-prod")
    dotted = root_dotted(os.path.join(d_new, "pl.json"))
    row("old CLI + new server", "--only-new: no dotted key at the root of pl.json",
        "GREEN" if not dotted else "RED", ",".join(dotted))
    for lang in ("pl", "de"):
        same = same_file(d_new, d_prod, f"{lang}.json")
        row("old CLI + new server", f"--only-new {lang}.json == old CLI + production",
            "GREEN" if same else "RED")
    for name, body, langs in (("i18next", json.dumps({"items_one": "{{count}} item",
                                                        "items_other": "{{count}} items"}), "pl,ar,ja"),
                              ("po", PO_SRC, "pl,ar,ja")):
        files = {}
        for srv in ("new", "prod"):
            d = fresh(f"old-full-{name}-{srv}")
            fn = "en.json" if name == "i18next" else "en.po"
            write(d, fn, body)
            run("046", srv, ["translate", fn, "--langs", langs, "--no-only-new", "--no-tm"], d)
            files[srv] = {l: read(d, f"{l}.{fn.split('.')[1]}") for l in langs.split(",")}
        row("old CLI + new server", f"full translate {name} {langs}: files == old CLI + production",
            "GREEN" if files["new"] == files["prod"] and None not in files["new"].values() else "RED")


# ── new CLI on the production server: no garbage, no endless --only-new ─────────────────────

def case_new_cli_prod_server():
    say("\n######## new CLI 0.2.47 + production server 94114a89")
    d, outs, checks = onlynew("new", "prod", "new-on-prod")
    dotted = root_dotted(os.path.join(d, "pl.json"))
    row("new CLI + prod", "--only-new: no dotted key at the root of pl.json",
        "GREEN" if not dotted else "RED", ",".join(dotted))
    sent = [o[2] for o in outs]
    up = [all(f"{l}: up to date" in o[1] for l in ("pl", "de")) for o in outs]
    row("new CLI + prod", "--only-new runs 2 and 3: up to date, nothing sent to the model",
        "GREEN" if up[1:] == [True, True] and sent[1:] == [0, 0] else "RED",
        f"model calls per run {sent}, up-to-date {up}")
    d_old, _, _ = onlynew("046", "prod", "046-on-prod-2")
    for lang in ("pl", "de"):
        same = same_file(d, d_old, f"{lang}.json")
        row("new CLI + prod", f"{lang}.json == 0.2.46 on production", "GREEN" if same else "RED")
    row("new CLI + prod", "check pl: forms production never writes are named (as with 0.2.46)",
        "info", f"check exits {checks}")
    # a target that has one/other only: missing forms alone are not work here
    d = fresh("new-on-prod-incomplete")
    write(d, "en.json", {"items_one": "{{count}} item", "items_other": "{{count}} items"})
    write(d, "pl.json", {"items_one": "{{count}} element", "items_other": "{{count}} elementów"})
    before = stub_calls()
    c1, o1 = run("new", "prod", ["translate", "en.json", "--langs", "pl", "--only-new", "--assume-current"], d)
    c2, o2 = run("new", "prod", ["translate", "en.json", "--langs", "pl", "--only-new"], d)
    row("new CLI + prod", "a pl target with one/other only: up to date twice, no model call",
        "GREEN" if "pl: up to date" in o1 and "pl: up to date" in o2 and stub_calls() == before else "RED",
        f"model calls {stub_calls() - before}")


# ── new CLI on the new server: every form, and honest memory numbers ───────────────────────

def case_new_new():
    say("\n######## new CLI 0.2.47 + new server")
    d, outs, checks = onlynew("new", "new", "new-on-new")
    pl = json.load(open(os.path.join(d, "pl.json"), encoding="utf-8"))
    ok = {"saved_few", "saved_many", "items_few", "items_many"} <= set(pl["cart"]) and \
        {"few", "many"} <= set(pl["files"]) and not root_dotted(os.path.join(d, "pl.json"))
    row("new CLI + new server", "--only-new: pl forms inside their objects", "GREEN" if ok else "RED")
    up = [all(f"{l}: up to date" in o[1] for l in ("pl", "de")) for o in outs]
    row("new CLI + new server", "--only-new runs 2 and 3: up to date, nothing sent",
        "GREEN" if up[1:] == [True, True] and [o[2] for o in outs][1:] == [0, 0] else "RED",
        f"model calls per run {[o[2] for o in outs]}")
    row("new CLI + new server", "check pl and de exit 0", "GREEN" if not any(checks.values()) else "RED",
        str(checks))
    # the two wordings: a set completed on its own, and a set sent beside an edited form
    d = fresh("wording")
    src = {"items_one": "{{count}} item", "items_other": "{{count}} items", "title": "Inbox"}
    write(d, "en.json", src)
    write(d, "pl.json", {"items_one": "{{count}} element", "items_other": "{{count}} elementów",
                         "title": "Skrzynka"})
    _, alone = run("new", "new", ["translate", "en.json", "--langs", "pl", "--only-new",
                                  "--assume-current", "--no-tm"], d)
    src["items_other"] = "{{count}} items in total"
    src["title"] = "Mail"
    write(d, "en.json", src)
    write(d, "pl.json", {"items_one": "{{count}} element", "items_other": "{{count}} elementów",
                         "items_few": "{{count}} elementy", "items_many": "{{count}} elementów",
                         "title": "Skrzynka"})
    _, beside = run("new", "new", ["translate", "en.json", "--langs", "pl", "--only-new", "--no-tm"], d)
    a = [l for l in alone.splitlines() if "plural sets" in l]
    b = [l for l in beside.splitlines() if "plural sets" in l]
    row("new CLI + new server", "set completed alone: 'sending … whole', no 'with them'; beside an "
        "edit: 'sent with them'",
        "GREEN" if a and all("sending 2 key(s) of plural sets whole" in l for l in a)
        and b and all("1 more key(s) of plural sets sent with them" in l for l in b) else "RED",
        " / ".join(a + b))
    # memory: second full run, what the CLI says it reuses vs what the server charges
    for tag, cli, srv in (("before", "cand", "cand"), ("after", "new", "new")):
        d = fresh(f"memory-{tag}")
        write(d, "en.json", {"items_one": "{{count}} item", "items_other": "{{count}} items",
                             "title": "Inbox", "save": "Save changes"})
        say(f"\n=== memory {tag}: {cli} on {srv}")
        run(cli, srv, ["translate", "en.json", "--langs", "de,pl,ja", "--no-only-new"], d)
        before = stub_calls()
        code, out = run(cli, srv, ["translate", "en.json", "--langs", "de,pl,ja", "--no-only-new"], d)
        line = next((l for l in out.splitlines() if "Project memory:" in l), "")
        n = int(re.search(r"(\d+) string", line).group(1)) if line else 0
        calls = stub_calls() - before
        if tag == "after":
            row("memory", "second full run: remembered lines counted = 10 (de 4, ja 4, pl 2: the "
                "pl set is translated again)", "GREEN" if n == 10 else "RED",
                f"said {n}; model calls {calls}")
        else:
            row("memory", f"{tag}: CLI said {n} remembered", "info", f"model calls {calls}")
    # npm translate on the new server: the forms arrive
    d = fresh("npm-new-on-new")
    write(d, "en.json", {"items_one": "{{count}} item", "items_other": "{{count}} items"})
    run("new", "new", ["translate", "en.json", "--langs", "pl", "--no-only-new"], d, "npm")
    pl = json.loads(read(d, "pl.json") or "{}")
    code, _ = run("new", "new", ["check", "--source", "en.json", "--langs", "pl"], d, "npm")
    row("new CLI + new server", "npm translate pl: items_few/items_many, check exit 0",
        "GREEN" if {"items_few", "items_many"} <= set(pl) and code == 0 else "RED")


# ── broken model answers ────────────────────────────────────────────────────────────────────

def english_left(d, lang, ext):
    body = read(d, f"{lang}.{ext}") or ""
    if ext == "json":
        flat = {}

        def walk(o, p=""):
            for k, v in o.items():
                walk(v, p + k + ".") if isinstance(v, dict) else flat.__setitem__(p + k, v)
        walk(json.loads(body or "{}"))
        return [k for k, v in flat.items() if re.search(r"\b(One|message|messages|from|Item|Items|day|days)\b", v)]
    return [l for l in body.splitlines() if l.startswith("msgstr") and re.search(r"[A-Za-z]{4,}", l)
            and ("delete" in l or "message" in l)]


def case_broken():
    say("\n######## broken model answers (new CLI + new server on a broken stub)")
    for mode in ("plain", "noother", "short"):
        srv = f"new-{mode}"
        for fn, body, ext in (("en.json", MIXED, "json"), ("en.po", PO_EDGE, "po")):
            d = fresh(f"broken-{mode}-{ext}")
            write(d, fn, body)
            say(f"\n=== broken {mode} {fn}")
            code, out = run("new", srv, ["translate", fn, "--langs", "pl,ar,ja", "--no-only-new", "--no-tm"], d)
            checks = {l: run("new", srv, ["check", "--source", fn, "--langs", l], d)[0] for l in ("pl", "ar", "ja")}
            say(f"--- {mode}/pl.{ext}\n{read(d, 'pl.' + ext)}")
            left = {l: english_left(d, l, ext) for l in ("pl", "ar", "ja")}
            row(f"broken {mode}", f"{fn}: no English source left in pl/ar/ja",
                "GREEN" if not any(left.values()) else "RED", str({k: v for k, v in left.items() if v}))
            qa = [l for l in out.splitlines() if "{count}" in l or "ICU" in l]
            row(f"broken {mode}", f"{fn}: QA says neither {{count}} nor ICU", "GREEN" if not qa else "RED",
                " / ".join(qa[:3]))
            row(f"broken {mode}", f"{fn}: check exits", "info", str(checks))


def main():
    os.makedirs(RUNS, exist_ok=True)
    procs = []
    try:
        for mode, port in STUBS.items():
            env = dict(os.environ, STUB_MODE=mode, STUB_LOG=os.path.join(RUNS, f"_stub-{mode}.jsonl"))
            if os.path.isfile(env["STUB_LOG"]):
                os.remove(env["STUB_LOG"])
            procs.append(subprocess.Popen([VENV_PY, os.path.join(HERE, "stub_model.py"), str(port)], env=env))
        for name, (srv, mode, port) in SERVERS.items():
            env = dict(os.environ, PYTHONUTF8="1", OPENROUTER_API_KEY="ci-not-a-real-key",
                       OPENROUTER_URL=f"http://127.0.0.1:{STUBS[mode]}/api/v1/chat/completions",
                       AUTO_TERMS="0", MAX_RETRIES="1", PYTHONDONTWRITEBYTECODE="1",
                       KAERIS_DATA_DIR=os.path.join(RUNS, f"_srvdata-{name}"))
            procs.append(subprocess.Popen(
                [VENV_PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
                 "--log-level", "warning"], cwd=os.path.join(SRV[srv], "backend"), env=env,
                stdout=open(os.path.join(RUNS, f"_server-{name}.log"), "w"), stderr=subprocess.STDOUT))
        say(f"# pids {' '.join(str(p.pid) for p in procs)}")
        for name, path in {**{f"cli {k}": v for k, v in CLI.items()},
                           **{f"server {k}": v for k, v in SRV.items()}}.items():
            head = subprocess.run(["git", "-C", path, "log", "-1", "--format=%h %s"], capture_output=True,
                                  text=True, encoding="utf-8").stdout.strip()[:80]
            say(f"# {name}: {path} @ {head}")
        for k in CLI:
            say(f"# kaeris {k} runs from: " + subprocess.run(
                [sys.executable, "-c", "import kaeris; print(kaeris.__file__, kaeris.__version__)"],
                env=cli_env(k, "new"), capture_output=True, text=True).stdout.strip())
        for name, (_, _, port) in SERVERS.items():
            if not wait_up(f"http://127.0.0.1:{port}/api/languages"):
                say(f"server {name} did not come up")
                return 2
        cfg = {n: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{SERVERS[n][2]}/api/config").read()).get(
            "plural_forms") for n in ("new", "cand", "prod")}
        say(f"# /api/config plural_forms: {cfg}")
        only = set(os.environ.get("COMPAT_ONLY", "").split(",")) - {""}
        for name, fn in (("b1", case_b1), ("b2", case_b2), ("oldnew", case_old_cli_new_server),
                         ("newprod", case_new_cli_prod_server), ("newnew", case_new_new),
                         ("broken", case_broken)):
            if not only or name in only:
                fn()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:
                p.kill()
        say(f"# stopped pids {' '.join(str(p.pid) for p in procs)}: rc {[p.poll() for p in procs]}")
        say("\n# SUMMARY")
        for case, what, verdict, detail in ROWS:
            say(f"  [{verdict}] {case}: {what}" + (f" — {detail}" if detail else ""))
        judged = [r for r in ROWS if r[2] in ("GREEN", "RED")]
        say(f"# {sum(r[2] == 'GREEN' for r in judged)}/{len(judged)} GREEN")
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    sys.exit(main() or 0)
