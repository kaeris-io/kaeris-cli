"""A stand-in for OpenRouter: answers chat/completions like a translator model, offline, $0.

Plain strings: every word is rewritten into the target script, placeholders survive.
An ICU plural string: the answer carries the plural categories a competent model writes for
the target language (pl/ru: one/few/many/other, ar/cy: all six, ja: one/other - the stray
`one` is what real models do and the server drops). This is what the real model did in the
round-3 acceptance run (pl ICU -> one/few/many/other). Any other call (repairs, judges): {}.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAMES = {"Polish": "pl", "Russian": "ru", "Arabic": "ar", "Japanese": "ja", "Welsh": "cy",
         "German": "de", "French": "fr", "Ukrainian": "uk"}
CATS = {"pl": ["one", "few", "many", "other"], "ru": ["one", "few", "many", "other"],
        "uk": ["one", "few", "many", "other"],
        "ar": ["zero", "one", "two", "few", "many", "other"],
        "cy": ["zero", "one", "two", "few", "many", "other"],
        "ja": ["one", "other"]}
SCRIPT = {"ru": "абвгдежзийклмнопрстуфхцчшщыэюя", "uk": "абвгдежзийклмнопрстуфхцчшщюяєії",
          "ar": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي", "ja": "アイウエオカキクケコサシスセソタチツテト"}
PH = re.compile(r"(\{\{[^{}]*\}\}|%\{[^{}]*\}|\{[^{}]*\}|%\d+\$[sd@]|%l{0,2}[sdu@]|<[^<>]+>|#)")
HEAD = re.compile(r"^\{\s*(\w+)\s*,\s*plural\s*,")


def word(w, lang):
    alpha = SCRIPT.get(lang)
    if alpha:
        return "".join(alpha[(ord(c.lower()) - 97) % len(alpha)] for c in w)
    return w[::-1].lower() + "y"


def plain(text, lang):
    out = []
    for part in PH.split(text):
        out.append(part if PH.fullmatch(part or "x") else re.sub(r"[A-Za-z]+", lambda m: word(m.group(0), lang), part))
    return "".join(out)


def arms(text):
    m = HEAD.match(text.strip())
    if not m:
        return None
    body = text.strip()[m.end():-1]
    found, i, depth, start, label = {}, 0, 0, 0, ""
    while i < len(body):
        ch = body[i]
        if ch == "{":
            if depth == 0:
                label = body[start:i].strip()
                arm_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                found[label] = body[arm_start:i]
                start = i + 1
        i += 1
    return (m.group(1), found) if "other" in found else None


def translate(text, lang):
    a = arms(text)
    if not a:
        return plain(text, lang)
    var, src = a
    out = []
    for cat in CATS.get(lang, ["one", "other"]):
        base = src.get(cat) or src.get("one" if cat == "one" else "other")
        out.append(f"{cat} {{{plain(base, lang)}{'' if cat in ('one', 'other') else ' ' + cat[:2]}}}")
    for label, body in src.items():
        if label.startswith("="):
            out.insert(0, f"{label} {{{plain(body, lang)}}}")
    return "{" + var + ", plural, " + " ".join(out) + "}"


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
        if m and m.group(1) in NAMES:
            lang = NAMES[m.group(1)]
            s, e = user.find("{"), user.rfind("}")
            cargo = json.loads(user[s:e + 1])
            reply = {k: {"t": translate(str(v), lang), "c": 96} for k, v in cargo.items()}
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
