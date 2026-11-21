"""diff_gate's stand-in for OpenRouter ($0, offline). The critic's round-4 stub (ops-logs
critic-p047-1121/round4/raw/stub4.py) with two modes more; the mode is read from MODE_FILE on
every request, flags comma separated:

  normal          a translator: words rewritten into the target script, placeholders kept; an
                  ICU plural answered with the target's CLDR categories (STUB CATS below)
  dropzero        the exact `=0` arm left out          drop:<cat>   that category left out
  hashall         the count written `#` in every arm ({{count}}, {{count, number}}, %d, %(x)d,
                  %1$d, {count}, {n}, %{count})
  missfold        every ICU plural left out of the reply (the server then has the source text)
  echo:<s>        a value holding <s> answered with itself
  empty           the reply is `{}` for every request (every value falls back to its source)
  fail500after1   HTTP 500 for every request of a language after its first one in this cell
                  (the gate writes `cell:<n>` into the mode, which resets the count): a retry,
                  a plural's second try, a repair all fail
  fail500key:<s>  HTTP 500 for a request holding a key that ends with <s>

Each server of the gate has its own stub (own counters). STUB_LOG: every cargo, one JSON line.
"""
import json, os, re, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAMES = {"Polish": "pl", "Russian": "ru", "Arabic": "ar", "Japanese": "ja", "Welsh": "cy",
         "German": "de", "French": "fr", "Ukrainian": "uk", "Chinese": "zh", "Korean": "ko",
         "Vietnamese": "vi", "Thai": "th", "Indonesian": "id", "Malay": "ms", "Hebrew": "he",
         "Latvian": "lv", "Czech": "cs", "English": "en", "Spanish": "es", "Slovenian": "sl", "Romanian": "ro", "Lithuanian": "lt"}
MODE_FILE = os.environ["MODE_FILE"]
LOG = os.environ.get("STUB_LOG")
LOCK = threading.Lock()
SEEN = {}          # (cell, lang) -> requests so far (fail500after1)
CATS = {"pl": ["one", "few", "many", "other"], "ru": ["one", "few", "many", "other"],
        "uk": ["one", "few", "many", "other"], "cs": ["one", "few", "many", "other"],
        "ar": ["zero", "one", "two", "few", "many", "other"],
        "cy": ["zero", "one", "two", "few", "many", "other"], "lv": ["zero", "one", "other"],
        "he": ["one", "two", "other"], "sl": ["one", "two", "few", "other"], "ro": ["one", "few", "other"], "lt": ["one", "few", "many", "other"], "fr": ["one", "many", "other"],
        "ja": ["one", "other"], "zh": ["other"], "ko": ["other"]}
SCRIPT = {"ru": "абвгдежзийклмнопрстуфхцчшщыэюя", "uk": "абвгдежзийклмнопрстуфхцчшщюяєії",
          "ar": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي", "ja": "アイウエオカキクケコサシスセソタチツテト",
          "he": "אבגדהוזחטיכלמנסעפצקרשת", "zh": "的一是不了人我在有他这中大来上国个到说们为子和你地出道也时年",
          "ko": "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허고노"}
PH = re.compile(r"(%\(\w+\)[sd]|\{\{[^{}]*\}\}|%\{[^{}]*\}|\{[^{}]*\}|%\d+\$[sd@]|%l{0,2}[sdu@]|<[^<>]+>|#)")
HEAD = re.compile(r"^\{\s*(\w+)\s*,\s*plural\s*,")


def mode():
    try:
        return [m.strip() for m in open(MODE_FILE, encoding="utf-8").read().split(",") if m.strip()]
    except Exception:
        return ["normal"]


def word(w, lang):
    a = SCRIPT.get(lang)
    if a:
        return "".join(a[(ord(c.lower()) - 97) % len(a)] for c in w)
    return w[::-1].lower() + "y"


def plain(text, lang):
    return "".join(p if PH.fullmatch(p or "x") else re.sub(r"[A-Za-z]+", lambda m: word(m.group(0), lang), p)
                   for p in PH.split(text))


def arms(text):
    m = HEAD.match(text.strip())
    if not m:
        return None
    body = text.strip()[m.end():-1]
    found, i, depth, start = {}, 0, 0, 0
    while i < len(body):
        ch = body[i]
        if ch == "{":
            if depth == 0:
                label = body[start:i].strip(); arm_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                found[label] = body[arm_start:i]; start = i + 1
        i += 1
    return (m.group(1), found) if "other" in found else None


def translate(text, lang, md):
    a = arms(text)
    if not a:
        return plain(text, lang)
    var, src = a
    cats = list(CATS.get(lang, ["one", "other"]))
    for f in md:
        if f.startswith("drop:"):
            cats = [c for c in cats if c != f[5:]]
    if "extrazero" in md and "zero" not in cats:
        cats.insert(0, "zero")
    out = []
    for cat in cats:
        base = src.get(cat) or src.get("one" if cat == "one" else "other")
        t = plain(base, lang) + ("" if cat in ("one", "other") else " " + cat[:2])
        if "hash" in md:
            t = re.sub(r"\{\{count\}\}|%\{count\}|%d|\{count\}", "#", t)
        if "hashall" in md:
            t = re.sub(r"\{\{\s*count[^{}]*\}\}|%\{count\}|%(?:\d+\$)?l*d|%\(\w+\)d|%\(count\)s|\{count\}|\{n\}|\{ ?\$count ?\}", "#", t)
        out.append(f"{cat} {{{t}}}")
    for label, body in src.items():
        if label.startswith("="):
            if "dropzero" in md:
                continue
            lab = "zero" if ("cldrzero" in md and label == "=0") else label
            if lab == "zero":
                out = [o for o in out if not o.startswith("zero {")]
            out.insert(0, f"{lab} {{{plain(body, lang)}}}")
    return "{" + ("n" if "varn" in md else var) + ", plural, " + " ".join(out) + "}"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = body.get("messages") or []
        system = " ".join(m["content"] for m in msgs if m.get("role") == "system" and isinstance(m.get("content"), str))
        user = msgs[-1]["content"] if msgs else ""
        if isinstance(user, list):
            user = next(p["text"] for p in user if p.get("type") == "text")
        m = re.search(r"Translate the JSON values below into ([A-Z][a-z]+)", system)
        reply = {}
        md = mode()
        if m and m.group(1) in NAMES:
            lang = NAMES[m.group(1)]
            s, e = user.find("{"), user.rfind("}")
            cargo = json.loads(user[s:e + 1])
            if LOG:
                with LOCK, open(LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"lang": lang, "mode": md, "cargo": cargo}, ensure_ascii=False) + "\n")
            cell = next((f for f in md if f.startswith("cell:")), "")
            with LOCK:
                seen = SEEN.setdefault((cell, lang), 0)
                SEEN[(cell, lang)] = seen + 1
            fail = (any(f.startswith("fail500key:") and any(k.endswith(f[11:]) for k in cargo) for f in md)
                    or ("fail500fold" in md and any(", plural," in str(v) for v in cargo.values()))
                    or ("fail500after1" in md and seen >= 1))
            if fail:
                self.send_response(500); self.send_header("Content-Length", "0"); self.end_headers()
                return
            for k, v in cargo.items():
                if "empty" in md:
                    break
                if any(f.startswith("echo:") and f[5:] in str(v) for f in md):
                    reply[k] = {"t": str(v), "c": 96}
                    continue
                if "missfold" in md and ", plural," in str(v):
                    continue
                if any(f.startswith("missalone:") and k.endswith(f[10:]) for f in md):
                    continue
                reply[k] = {"t": translate(str(v), lang, md), "c": 96}
        elif LOG:
            with LOCK, open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"other_call": system[:200]}, ensure_ascii=False) + "\n")
        data = json.dumps({"choices": [{"message": {"content": json.dumps(reply, ensure_ascii=False)},
                                        "finish_reason": "stop"}],
                           "model": body.get("model", "stub"), "provider": "stub",
                           "usage": {"prompt_tokens": 10, "completion_tokens": 10}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
