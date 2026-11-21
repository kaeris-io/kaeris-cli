"""diff_gate.py: the differential gate of P0.2.47 (round 5). Every cell is run twice and compared:

  new -> new     this kaeris-cli tree      ->  this i18n_tool branch (plurals=cldr)
  046 -> prod    kaeris-cli d5535f0 (0.2.46) ->  i18n_tool 94114a89 (production)
  046 -> new     kaeris-cli d5535f0 (0.2.46) ->  this i18n_tool branch (an old client, no field)

What is compared per cell (format x stub mode x language): the language's file, byte for byte;
`kaeris check --json` of 0.2.46 and of this tree on it (exit code, faults, missing/extra keys,
warnings); and per run the exit code of translate and the characters charged (the receipt's
metered count). `--only-new` (the GitHub Action's mode) is run on JSON twice from an empty target,
and once more by this tree on the target 0.2.46 left (the upgrade), then again.

  046 -> new  vs  046 -> prod: must be the same in everything. Any difference is red.
  new -> new  vs  046 -> prod: a difference is green only when it is one of INTENDED below and
                               passes that entry's guard; every other difference is red.

usage: python diff_gate.py --prod <i18n_tool at 94114a89> --cli046 <kaeris-cli at d5535f0>
                           [--server <i18n_tool branch>] [--runs <dir>] [--out <report.txt>]
                           [--modes m1,m2] [--formats f1,f2] [--no-only-new]

Servers and the stub run only while the gate runs (three uvicorns, three stubs, each stopped by
its own PID at the end). The model is the offline stub (gate_stub.py): $0, no key.
"""
import argparse
import importlib
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
CLI_NEW = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RUN_CLI = os.path.join(HERE, "run_cli.py")
GATE_CHECK = os.path.join(HERE, "gate_check.py")
STUB = os.path.join(HERE, "gate_stub.py")
DEFAULT_SERVER = r"C:\Users\Inzagi\projects\kaeris\i18n_tool\.claude\worktrees\plural-translate-1121"
VENV_PY = r"C:\Users\Inzagi\projects\kaeris\i18n_tool\.venv\Scripts\python.exe"
PORTS = {"stub-nn": 18990, "stub-on": 18991, "stub-op": 18992, "nn": 18993, "on": 18994, "op": 18995}
PAIRS = {"nn": ("new", "nn"), "op": ("046", "op"), "on": ("046", "on")}

LANGS = ["de", "pl", "ru", "ar", "lv", "he", "ja", "zh", "ko"]
LANG_RUNS = (LANGS[:5], LANGS[5:])
REFUSED = "cy"          # not one of the server's languages: refused alike, run on its own
MODES = ["normal", "dropzero", "drop:zero", "drop:one", "drop:two", "drop:few", "drop:many",
         "hashall", "missfold", "echo:file", "empty", "fail500after1"]

HEAD = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n"Language: en\\n"\n\n')


def _po(*entries):
    out = [HEAD]
    for flag, one, other in entries:
        out.append((f"#, {flag}\n" if flag else "") + f'msgid "{one}"\n' +
                   (f'msgid_plural "{other}"\nmsgstr[0] ""\nmsgstr[1] ""\n\n' if other is not None
                    else 'msgstr ""\n\n'))
    return "".join(out)


# The placeholder styles of the brief, each where its format has it: {{count}}, {{ count }},
# {{count, number}}, %d, %(count)s / %(count)d, {count}, %{count}, a `#` of the source's own, a
# second placeholder every form shares, a singular without the number, an ordinal set, `_zero`.
FORMATS = {
    "i18next": ("en.json", "json", json.dumps({
        "title": "Inbox",
        "cart_zero": "Your cart is empty", "cart_one": "{{count}} item in your cart",
        "cart_other": "{{count}} items in your cart",
        "msg_one": "One message from {{name}}", "msg_other": "{{count}} messages from {{name}}",
        "num_one": "{{count, number}} file", "num_other": "{{count, number}} files",
        "post_one": "{{count}} post in #general", "post_other": "{{count}} posts in #general",
        "in_one": "{{count}} item in {{folder}}", "in_other": "{{count}} items in {{folder}}",
        "sp_one": "{{ count }} day", "sp_other": "{{ count }} days",
        "place_ordinal_one": "{{count}}st place", "place_ordinal_two": "{{count}}nd place",
        "place_ordinal_few": "{{count}}rd place", "place_ordinal_other": "{{count}}th place",
    }, ensure_ascii=False, indent=2)),
    "nested": ("en.json", "json", json.dumps({"inbox": {
        "title": "Inbox",
        "box": {"zero": "Nothing here", "one": "{{count}} box", "other": "{{count}} boxes"},
        "msg": {"one": "One message from {{name}}", "other": "{{count}} messages from {{name}}"},
        "post": {"one": "{{count}} post in #general", "other": "{{count}} posts in #general"},
        "num": {"one": "{{count, number}} file", "other": "{{count, number}} files"},
    }}, ensure_ascii=False, indent=2)),
    "rails": ("en.yml", "yaml", (
        'en:\n  title: "Inbox"\n'
        '  cart:\n    zero: "Your cart is empty"\n    one: "%{count} item"\n    other: "%{count} items"\n'
        '  msg:\n    one: "One message from %{name}"\n    other: "%{count} messages from %{name}"\n'
        '  post:\n    one: "%{count} post in #general"\n    other: "%{count} posts in #general"\n'
        '  file:\n    one: "%{count} file"\n    other: "%{count} files"\n')),
    "po-printf": ("en.po", "po", _po(
        ("c-format", "%d file", "%d files"), ("c-format", "One message", "%d messages"),
        ("c-format", "One message from %s", "%d messages from %s"),
        ("c-format", "%d post in #general", "%d posts in #general"),
        ("c-format", "%1$d of %2$s page", "%1$d of %2$s pages"), (None, "Inbox", None))),
    "po-python": ("en.po", "po", _po(
        ("python-format", "%(count)d file", "%(count)d files"),
        ("python-format", "One file", "%(count)s files"),
        ("python-format", "One message from %(name)s", "%(count)d messages from %(name)s"),
        ("python-format", "%(count)s post in #general", "%(count)s posts in #general"),
        ("python-format", "%(num)d page", "%(num)d pages"), (None, "Inbox", None))),
    "po-brace": ("en.po", "po", _po(
        ("python-brace-format", "{count} cat", "{count} cats"),
        ("python-brace-format", "One file", "{count} files"),
        ("python-brace-format", "One message from {name}", "{count} messages from {name}"),
        ("python-brace-format", "{count} post in #general", "{count} posts in #general"),
        (None, "Inbox", None))),
    "android": ("res/values/strings.xml", "xml", (
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="title">Inbox</string>\n'
        '    <plurals name="files">\n        <item quantity="one">%d file</item>\n'
        '        <item quantity="other">%d files</item>\n    </plurals>\n'
        '    <plurals name="msgs">\n        <item quantity="one">One message</item>\n'
        '        <item quantity="other">%d messages</item>\n    </plurals>\n'
        '    <plurals name="in">\n        <item quantity="one">%1$d file in %2$s</item>\n'
        '        <item quantity="other">%1$d files in %2$s</item>\n    </plurals>\n'
        '    <plurals name="post">\n        <item quantity="one">%d post in #general</item>\n'
        '        <item quantity="other">%d posts in #general</item>\n    </plurals>\n</resources>\n')),
    "fluent": ("en.ftl", "ftl", (
        'title = Inbox\nfiles = { $count ->\n    [one] { $count } file\n   *[other] { $count } files\n}\n'
        'msgs = { $count ->\n    [one] One message\n   *[other] { $count } messages\n}\n'
        'post = { $count ->\n    [one] { $count } post in #general\n   *[other] { $count } posts in #general\n}\n')),
    "icu-json": ("en.json", "json", json.dumps({
        "title": "Inbox",
        "files": "{count, plural, one {# file} other {# files}}",
        "msg": "{count, plural, =0 {No messages} one {One message from {name}} other {# messages from {name}}}",
        "items": "{n, plural, one {{n} item} other {{n} items}}",
    }, ensure_ascii=False, indent=2)),
}
ONLY_NEW_FORMATS = ("i18next", "nested", "icu-json")

# Differences that are the package, each with its reason and the guard it must pass (see
# classify). Nothing else may differ.
INTENDED = {
    "cldr-forms": "a JSON/YAML plural set gets the forms its target language needs that the source "
                  "lacks (pl/ru few+many, ar zero..many, lv zero, he two): new keys beside the set, "
                  "the set's own forms written from the one folded answer. Guard: only keys of "
                  "plural sets differ, no key is lost, check 0.2.46 and 0.2.47 report nothing the "
                  "0.2.46 file did not have",
    "po-slots": "a .po plural entry laid out slot by slot in the target's Plural-Forms order "
                "(pl msgstr[2] is the many form; ar six own forms; ja/zh/ko one slot = the plural "
                "form where a lone %d lets check take it). Guard: header and every non-plural "
                "entry byte-identical, check 0.2.47 reports nothing new, check 0.2.46 nothing new "
                "but po-single-slot-046",
    "po-single-slot-046": "Arabic/Hebrew msgstr[1]/[2] (a slot one number picks) without %d: check "
                          "0.2.46 calls it a lost placeholder, 0.2.47 reads it (release notes, "
                          "'The reverse is not true')",
    "onlynew-complete": "--only-new by this CLI on a target 0.2.46 wrote: a set that lacks a form "
                        "its language needs is sent once, whole, and charged; written with every "
                        "form (cldr-forms guard on the file). The next run must charge nothing",
}


def say(log, s=""):
    log.write(s + "\n")
    log.flush()
    print(s, flush=True)


def wait_up(url, secs=120):
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


class Gate:
    def __init__(self, a):
        self.a = a
        self.runs = os.path.abspath(a.runs)
        self.mode_file = os.path.join(self.runs, "_mode.txt")
        self.cli = {"new": CLI_NEW, "046": os.path.abspath(a.cli046)}
        self.srv = {"nn": a.server, "on": a.server, "op": os.path.abspath(a.prod)}
        self.cell_no = 0
        self.rows = []        # (kind, where, verdict, tag, detail)
        sys.path.insert(0, CLI_NEW)
        self.fm = importlib.import_module("kaeris.formats")
        self.inc = importlib.import_module("kaeris.incremental")
        self.chk = importlib.import_module("kaeris.check")

    # ── processes ────────────────────────────────────────────────────────────────────────
    def start(self, log):
        os.makedirs(self.runs, exist_ok=True)
        open(self.mode_file, "w").write("normal")
        self.procs = []
        for pair in ("nn", "on", "op"):
            env = dict(os.environ, MODE_FILE=self.mode_file,
                       STUB_LOG=os.path.join(self.runs, f"_stub-{pair}.jsonl"))
            self.procs.append(subprocess.Popen([VENV_PY, STUB, str(PORTS["stub-" + pair])], env=env))
        for pair in ("nn", "on", "op"):
            env = dict(os.environ, PYTHONUTF8="1", OPENROUTER_API_KEY="ci-not-a-real-key",
                       OPENROUTER_URL=f"http://127.0.0.1:{PORTS['stub-' + pair]}/api/v1/chat/completions",
                       AUTO_TERMS="0", MAX_RETRIES="1", PYTHONDONTWRITEBYTECODE="1",
                       # ~1500 keyless runs in one gate: the day's free allowance of one
                       # address would run out halfway (HTTP 429), the same on every server
                       ANON_DAILY_CHAR_CAP="1000000000", ANON_DAILY_CHAR_CAP_PER_IP="1000000000",
                       KAERIS_DATA_DIR=os.path.join(self.runs, f"_srvdata-{pair}"))
            self.procs.append(subprocess.Popen(
                [VENV_PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORTS[pair]),
                 "--log-level", "warning"], cwd=os.path.join(self.srv[pair], "backend"), env=env,
                stdout=open(os.path.join(self.runs, f"_server-{pair}.log"), "w"), stderr=subprocess.STDOUT))
        say(log, f"# pids {' '.join(str(p.pid) for p in self.procs)}")
        for pair in ("nn", "on", "op"):
            if not wait_up(f"http://127.0.0.1:{PORTS[pair]}/api/languages"):
                raise SystemExit(f"server {pair} did not come up")
            cfg = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORTS[pair]}/api/config").read())
            head = subprocess.run(["git", "-C", self.srv[pair], "rev-parse", "--short", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            say(log, f"# server {pair} ({head}) up, plural_forms={cfg.get('plural_forms')!r}")
        for name, tree in self.cli.items():
            head = subprocess.run(["git", "-C", tree, "rev-parse", "--short", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            say(log, f"# cli {name} = {tree} ({head})")

    def stop(self, log):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except Exception:
                p.kill()
        say(log, f"# stopped pids {' '.join(str(p.pid) for p in self.procs)}: rc {[p.poll() for p in self.procs]}")

    def mode(self, m):
        self.cell_no += 1
        open(self.mode_file, "w", encoding="utf-8").write(f"{m},cell:{self.cell_no}")

    def translate(self, pair, d, args):
        cli, port_key = PAIRS[pair]
        env = dict(os.environ, PYTHONUTF8="1", CI="1", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1",
                   KAERIS_API_URL=f"http://127.0.0.1:{PORTS[port_key]}")
        env.pop("KAERIS_API_KEY", None)
        for f in os.listdir(d):
            if f.startswith("receipt"):
                os.remove(os.path.join(d, f))
        p = subprocess.run([sys.executable, RUN_CLI, self.cli[cli], *args, "--receipt", "receipt.json"],
                           cwd=d, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        out = p.stdout + p.stderr
        with open(os.path.join(d, f"_out-{self.cell_no}.txt"), "w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(args)} -> exit {p.returncode}\n{out}")
        return p.returncode, out, self.charged(d, out)

    @staticmethod
    def charged(d, out):
        """The characters charged: the receipt's metered count(s), else the printed line(s)."""
        path = os.path.join(d, "receipt.json")
        found = []
        if os.path.isfile(path):
            try:
                doc = json.load(open(path, encoding="utf-8"))
            except ValueError:
                doc = None

            def walk(x, key=""):
                if isinstance(x, dict):
                    for k, v in x.items():
                        walk(v, k)
                elif isinstance(x, list):
                    for v in x:
                        walk(v, key)
                elif key == "metered" and isinstance(x, (int, float)):
                    found.append(int(x))
            walk(doc)
        if found:
            return sum(found)
        printed = re.findall(r"([\d.]+[kM]?) charged", out)
        return "+".join(printed) if printed else 0

    def check(self, cli, d, src):
        p = subprocess.run([sys.executable, GATE_CHECK, self.cli[cli], d, src, ",".join(LANGS)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=600, env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
        try:
            return json.loads(p.stdout)["res"]
        except (ValueError, KeyError):
            return {lang: {"code": "crash", "result": None, "out": (p.stdout + p.stderr)[-400:]}
                    for lang in LANGS}

    # ── files ────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def files(d, src):
        out = {}
        for root, _dirs, names in os.walk(d):
            for n in names:
                p = os.path.join(root, n)
                rel = os.path.relpath(p, d).replace("\\", "/")
                if rel == src or rel.startswith(("kaeris-tm", ".", "receipt", "_out")):
                    continue
                out[rel] = open(p, "rb").read()
        return out

    @staticmethod
    def target(fmt, lang):
        src, kind, _ = FORMATS[fmt]
        if kind == "xml":
            return f"res/values-{lang}/strings.xml"
        return f"{lang}{os.path.splitext(src)[1]}"

    def flat(self, kind, data):
        text = data.decode("utf-8")
        if kind == "yaml":
            return dict(self.fm.read_yaml(text))
        return self.inc.flatten(json.loads(text))

    @staticmethod
    def po_entries(data):
        text = data.decode("utf-8")
        blocks = text.split("\n\n")
        head, entries = blocks[0], {}
        for b in blocks[1:]:
            mid = re.search(r'^msgid "(.*)"$', b, re.M)
            if not mid:
                continue
            plural = re.search(r'^msgid_plural "(.*)"$', b, re.M) is not None
            entries[mid.group(1)] = (plural, b)
        return head, entries

    def plural_keys(self, fmt):
        """Keys a plural set of the source may have in a target: its members and every CLDR
        form of its base (not an ordinal set)."""
        src, kind, body = FORMATS[fmt]
        flat = self.flat(kind, body.encode())
        keys = set()
        for (base, sep), _forms in self.chk._plural_sets(flat).items():
            if sep == "_" and base.endswith("_ordinal"):
                continue
            keys.update(f"{base}{sep}{c}" for c in ("zero", "one", "two", "few", "many", "other"))
        return keys

    # ── comparison ───────────────────────────────────────────────────────────────────────
    @staticmethod
    def findings(res):
        """What a check said, as a set of strings (empty when it said nothing)."""
        if res is None:
            return {"<no file>"}
        r = res.get("result")
        if r is None:
            return {f"<exit {res.get('code')}: {res.get('out')}>"}
        out = set()
        for k in ("faults", "warnings", "placeholder_issues"):
            for f in r.get(k) or []:
                out.add(f"{k}: " + (json.dumps(f, ensure_ascii=False, sort_keys=True)
                                    if not isinstance(f, str) else f))
        for k in ("missing", "extra"):
            for lang, keys in (r.get(k) or {}).items():
                out.update(f"{k}: {key}" for key in keys)
        out.update(f"missing_file: {m}" for m in r.get("missing_files") or [])
        return out

    @staticmethod
    def single_slot_046(fmt, lang, extra):
        """po-single-slot-046: check 0.2.46's lost %d on a slot one number picks (ar/he)."""
        slots = {"ar": r"⟦plural(:2)?⟧", "he": r"⟦plural⟧"}.get(lang, r"$^")   # n == 1 / n == 2 only

        def one(f):
            return re.search(r'"key": "[^"]*' + slots + '"', f) and (
                re.search(r'"msg": "lost placeholder %\d*\$?l*d"', f) or
                re.search(r'"added": \[\], .*"missing": \["%\d*\$?l*d"\]', f))
        return bool(fmt.startswith("po") and lang in ("ar", "he") and extra and all(one(f) for f in extra))

    def classify(self, fmt, lang, old, new, chk_old, chk_new):
        """('same' | 'intended' | 'RED', tag, detail) for one language's file and checks."""
        _src, kind, _body = FORMATS[fmt]
        f_old = {v: self.findings(chk_old[v].get(lang)) for v in ("046", "new")}
        f_new = {v: self.findings(chk_new[v].get(lang)) for v in ("046", "new")}
        c_old = {v: (chk_old[v].get(lang) or {}).get("code") for v in ("046", "new")}
        c_new = {v: (chk_new[v].get(lang) or {}).get("code") for v in ("046", "new")}
        if old == new:
            if f_old == f_new and c_old == c_new:
                return "same", "", ""
            return "RED", "check", f"same file, other check: {f_old} vs {f_new}"
        if old is None or new is None:
            return "RED", "delivery", f"file {'missing in 046->prod' if old is None else 'missing in new->new'}"
        if kind in ("xml", "ftl") or fmt == "icu-json":
            return "RED", "bytes", "this format has no intended difference"
        tags = []
        if kind in ("json", "yaml"):
            try:
                a, b = self.flat(kind, old), self.flat(kind, new)
            except Exception as e:      # noqa: BLE001
                return "RED", "parse", repr(e)
            lost = sorted(set(a) - set(b))
            if lost:
                return "RED", "keys", f"keys lost: {lost}"
            allowed = self.plural_keys(fmt)
            other = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k not in allowed)
            if other:
                return "RED", "keys", f"not plural keys differ: {other}"
            tags.append("cldr-forms")
        else:       # po
            ha, ea = self.po_entries(old)
            hb, eb = self.po_entries(new)
            if ha != hb:
                return "RED", "header", "header differs"
            if set(ea) != set(eb):
                return "RED", "entries", f"entries differ: {sorted(set(ea) ^ set(eb))}"
            bad = sorted(m for m in ea if ea[m] != eb[m] and not ea[m][0])
            if bad:
                return "RED", "entries", f"non-plural entries differ: {bad}"
            tags.append("po-slots")
        if not f_new["new"] <= f_old["new"] or (c_new["new"] or 0) > (c_old["new"] or 0):
            return "RED", "check047", f"new findings: {sorted(f_new['new'] - f_old['new'])}"
        extra046 = f_new["046"] - f_old["046"]
        if extra046:
            if not self.single_slot_046(fmt, lang, extra046):
                return "RED", "check046", f"new findings: {sorted(extra046)}"
            tags.append("po-single-slot-046")
        return "intended", "+".join(tags), ""

    def row(self, log, kind, where, verdict, tag="", detail=""):
        self.rows.append((kind, where, verdict, tag, detail))
        if verdict != "same" or self.a.verbose:
            say(log, f"  [{verdict}] {kind} {where}" + (f" <{tag}>" if tag else "") +
                (f": {detail}" if detail else ""))

    # ── the cells ────────────────────────────────────────────────────────────────────────
    def full(self, log, mode, fmt):
        src, kind, body = FORMATS[fmt]
        got = {}
        for pair in ("nn", "op", "on"):
            d = os.path.join(self.runs, mode.replace(":", "_"), fmt, pair)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(os.path.join(d, src)), exist_ok=True)
            with open(os.path.join(d, src), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            # without a key a run takes 8 languages: two runs, as a user without a key makes them
            rc, out, money = 0, "", 0
            for group in LANG_RUNS:
                args = ["translate", src, "--langs", ",".join(group), "--no-tm"]
                if kind == "json":
                    args.append("--no-only-new")
                self.mode(mode)
                rc1, out1, money1 = self.translate(pair, d, args)
                rc, out = max(rc, rc1), out + out1
                money = money + money1 if isinstance(money, int) and isinstance(money1, int)                     else f"{money}+{money1}"
            chk = {"046": self.check("046", d, src), "new": self.check("new", d, src)}
            got[pair] = (rc, money, self.files(d, src), chk, out)
        self.compare_runs(log, f"{mode:13} {fmt:9}", fmt, got)

    def compare_runs(self, log, where, fmt, got, base="op", pairs=("on", "nn"), tag_money=None):
        b_rc, b_money, b_files, b_chk, b_out = got[base]
        if b_rc not in (0, 3) or not any(self.target(fmt, l) in b_files for l in LANGS) and b_rc != 3:
            # a run that wrote nothing without saying a language fell back is the harness's fault
            # (a flag, a path), and two such runs would compare as "the same"
            self.row(log, "run", f"{where} {base} sane", "RED", "harness",
                     f"exit {b_rc}, files {sorted(b_files)}; "
                     + " | ".join(l.strip() for l in b_out.splitlines()[-4:])[:400])
        for pair in pairs:
            rc, money, files, chk, out = got[pair]
            label = f"{where} {pair}~{base}"
            # the run
            if (rc, money) == (b_rc, b_money):
                self.row(log, "run", label, "same")
            elif pair == "nn" and tag_money and tag_money(rc, money, b_rc, b_money):
                self.row(log, "run", label, "intended", "onlynew-complete",
                         f"exit {rc} vs {b_rc}, charged {money} vs {b_money}")
            else:
                self.row(log, "run", label, "RED", "run",
                         f"exit {rc} vs {b_rc}, charged {money} vs {b_money}; out: "
                         + " | ".join(l.strip() for l in out.splitlines()[-6:])[:600])
            # every file that is not a language's own (the lock) must be the same for the old CLI
            for lang in LANGS:
                t = self.target(fmt, lang)
                old, new = b_files.get(t), files.get(t)
                if pair == "on":
                    v = ("same" if old == new and all(
                        self.findings(chk[x].get(lang)) == self.findings(b_chk[x].get(lang)) and
                        (chk[x].get(lang) or {}).get("code") == (b_chk[x].get(lang) or {}).get("code")
                        for x in ("046", "new")) else "RED")
                    self.row(log, "cell", f"{label} {lang}", v, "" if v == "same" else "old-client",
                             "" if v == "same" else _diff(old, new))
                else:
                    v, tag, detail = self.classify(fmt, lang, old, new, b_chk, chk)
                    self.row(log, "cell", f"{label} {lang}", v, tag,
                             detail + ("" if v != "RED" else " | " + _diff(old, new)))
            if pair == "on":
                rest_b = {k: v for k, v in b_files.items() if not any(k == self.target(fmt, l) for l in LANGS)}
                rest = {k: v for k, v in files.items() if not any(k == self.target(fmt, l) for l in LANGS)}
                if rest != rest_b:
                    self.row(log, "cell", f"{label} other-files", "RED", "old-client",
                             f"{sorted(set(rest) ^ set(rest_b))} / changed "
                             f"{[k for k in rest if rest.get(k) != rest_b.get(k)]}")

    def refused(self, log, fmt):
        src, kind, body = FORMATS[fmt]
        got = {}
        for pair in ("nn", "op", "on"):
            d = os.path.join(self.runs, "refused", fmt, pair)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(os.path.join(d, src)), exist_ok=True)
            with open(os.path.join(d, src), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            self.mode("normal")
            rc, out, money = self.translate(pair, d, ["translate", src, "--langs", REFUSED, "--no-tm"])
            got[pair] = (rc, money, sorted(self.files(d, src)))
        for pair in ("on", "nn"):
            v = "same" if got[pair] == got["op"] else "RED"
            self.row(log, "run", f"{'normal':13} {fmt:9} {pair}~op {REFUSED}", v,
                     "" if v == "same" else "refused", f"{got[pair]} vs {got['op']}")

    def only_new(self, log, mode, fmt):
        src, kind, body = FORMATS[fmt]
        args = ["translate", src, "--langs", ",".join(LANGS), "--only-new", "--no-tm"]
        root = os.path.join(self.runs, mode.replace(":", "_"), fmt + "-onlynew")
        shutil.rmtree(root, ignore_errors=True)
        first, second = {}, {}
        for pair in ("nn", "op", "on"):
            d = os.path.join(root, pair)
            os.makedirs(d)
            with open(os.path.join(d, src), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            self.mode(mode)
            rc, out, money = self.translate(pair, d, args)
            chk = {"046": self.check("046", d, src), "new": self.check("new", d, src)}
            first[pair] = (rc, money, self.files(d, src), chk, out)
            if pair == "op":            # the upgrade: this CLI on what 0.2.46 left
                shutil.copytree(d, os.path.join(root, "up"))
            self.mode(mode)
            rc2, out2, money2 = self.translate(pair, d, args)
            second[pair] = (rc2, money2, self.files(d, src), chk, out2)
        where = f"{mode:13} {fmt + '/on1':13}"
        self.compare_runs(log, where, fmt, first)
        for pair in ("nn", "op", "on"):
            rc, money, files, _c, out = second[pair]
            ok = money == 0 and files == first[pair][2] and rc == first[pair][0]
            self.row(log, "run", f"{mode:13} {fmt + '/on2':13} {pair} up to date", "same" if ok else "RED",
                     "" if ok else "money", "" if ok else
                     f"exit {rc}, charged {money}, files changed "
                     f"{[k for k in files if files[k] != first[pair][2].get(k)]}; "
                     + " | ".join(l.strip() for l in out.splitlines()[-5:])[:500])
        # the upgrade: run this CLI twice on the target and lock 0.2.46 wrote
        d = os.path.join(root, "up")
        base = {"op": second["op"]}
        self.mode(mode)
        rc, out, money = self.translate("nn", d, args)
        chk = {"046": self.check("046", d, src), "new": self.check("new", d, src)}
        base["nn"] = (rc, money, self.files(d, src), chk, out)
        self.compare_runs(log, f"{mode:13} {fmt + '/up1':13}", fmt, base, pairs=("nn",),
                          tag_money=lambda rc, m, brc, bm: rc == brc and (m or 0) > 0)
        self.mode(mode)
        rc2, out2, money2 = self.translate("nn", d, args)
        ok = money2 == 0 and self.files(d, src) == base["nn"][2] and rc2 == rc
        self.row(log, "run", f"{mode:13} {fmt + '/up2':13} nn up to date", "same" if ok else "RED",
                 "" if ok else "money", "" if ok else f"exit {rc2}, charged {money2}; "
                 + " | ".join(l.strip() for l in out2.splitlines()[-5:])[:500])


def _diff(a, b, width=420):
    if a == b:
        return ""
    a = a.decode("utf-8", "replace") if isinstance(a, bytes) else str(a)
    b = b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)
    la, lb = a.splitlines(), b.splitlines()
    out = [f"-{x}" for x in la if x not in lb][:6] + [f"+{x}" for x in lb if x not in la][:6]
    return " ".join(out)[:width]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", required=True)
    ap.add_argument("--cli046", required=True)
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--runs", default=os.path.join(os.getcwd(), "gate-runs"))
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "diff-gate.txt"))
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--no-only-new", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    g = Gate(a)
    log = open(a.out, "w", encoding="utf-8")
    t0 = time.time()
    say(log, f"# diff_gate {time.strftime('%Y-%m-%d %H:%M')}; langs {LANGS} (+{REFUSED} refused); "
             f"modes {a.modes}; formats {a.formats}")
    say(log, "# intended differences (anything else is red):")
    for k, v in INTENDED.items():
        say(log, f"#   {k}: {v}")
    g.start(log)
    try:
        fmts = a.formats.split(",")
        for fmt in fmts:
            g.refused(log, fmt)
        for mode in a.modes.split(","):
            say(log, f"## mode {mode}")
            for fmt in fmts:
                g.full(log, mode, fmt)
                if not a.no_only_new and fmt in ONLY_NEW_FORMATS:
                    g.only_new(log, mode, fmt)
    finally:
        g.stop(log)
    cells = [r for r in g.rows if r[0] == "cell"]
    runs = [r for r in g.rows if r[0] == "run"]
    old = [r for r in g.rows if "on~" in r[1]]
    red = [r for r in g.rows if r[2] == "RED"]
    intended = [r for r in g.rows if r[2] == "intended"]
    by_tag = {}
    for r in intended:
        by_tag[r[3]] = by_tag.get(r[3], 0) + 1
    say(log, "")
    say(log, f"# intended by tag: {json.dumps(by_tag, sort_keys=True)}")
    say(log, f"# old client -> new server: {len(old)} comparisons, "
             f"{sum(1 for r in old if r[2] == 'RED')} differences")
    say(log, f"TOTAL {len(cells)} cells + {len(runs)} runs, {len(intended)} intended, "
             f"{len(red)} unintended ({time.time() - t0:.0f}s)")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
