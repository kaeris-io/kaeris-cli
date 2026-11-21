"""B2 (critic 21.11): `kaeris check` py + npm next to gettext's `msgfmt -c` on every .po case of
tests/test_po_single_number_slots.py (the loose single-number slots and the cases they must not
let through). usage: python b2_msgfmt.py <cli-worktree> [msgfmt.exe]
Prints one row per case: expected, py exit, npm exit, msgfmt -c exit + its first error line."""
import importlib.util
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CLI = sys.argv[1]
MSGFMT = sys.argv[2] if len(sys.argv) > 2 else r"C:\msys64\usr\bin\msgfmt.exe"
spec = importlib.util.spec_from_file_location("slots", os.path.join(CLI, "tests", "test_po_single_number_slots.py"))
T = importlib.util.module_from_spec(spec)
sys.path.insert(0, CLI)
spec.loader.exec_module(T)
env = dict(os.environ, PYTHONPATH=CLI, PYTHONUTF8="1", NO_COLOR="1")
import kaeris  # noqa: E402
print(f"# kaeris {kaeris.__file__}")


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


print(f"{'case':38} {'expect':6} {'py':>3} {'npm':>4} {'msgfmt':>6}  msgfmt says")
for name in sorted(T.CASES):
    lang, _rule, _m, _f, passes = T.CASES[name]
    with tempfile.TemporaryDirectory() as d:
        for fn, body in T.files(name).items():
            with open(os.path.join(d, fn), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
        py, _ = run([sys.executable, "-m", "kaeris", "check", "--source", "en.po", "--langs", lang], d)
        npm, _ = run(["node", os.path.join(CLI, "npm", "bin", "kaeris.js"), "check", "--source", "en.po",
                      "--langs", lang], d)
        # msgfmt needs a charset, and checks %d only on a c-format entry
        body = T.files(name)[f"{lang}.po"].replace(
            'msgstr ""\n', 'msgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n', 1)
        body = body.replace('\nmsgid "', '\n#, c-format\nmsgid "')
        with open(os.path.join(d, "mf.po"), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        mf, mtxt = run([MSGFMT, "-c", "-o", "mf.mo", "mf.po"], d)
        first = " / ".join(l.split(": ", 1)[-1] for l in mtxt.splitlines()
                           if "warning: header field" not in l and "found" not in l and l.strip()) or "ok"
        print(f"{name:38} {'pass' if passes else 'fail':6} {py:>3} {npm:>4} {mf:>6}  {first[:110]}")
