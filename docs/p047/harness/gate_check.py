"""gate_check.py <cli-tree> <workdir> <source> <lang,lang,...>: `kaeris check --json` of the CLI in
<cli-tree> (whatever kaeris is installed: the tree goes first, as in run_cli.py) for each language
on its own, in one process. Prints one JSON object {lang: {"code": exit code, "result": the check's
JSON or null, "out": what it printed when that was not JSON}} and the file that answered.
"""
import contextlib
import io
import json
import os
import sys

tree, workdir, source, langs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(",")
sys.path.insert(0, tree)
for name in list(sys.modules):
    if name == "kaeris" or name.startswith("kaeris."):
        del sys.modules[name]
os.environ.update(CI="1", NO_COLOR="1", PYTHONUTF8="1")
os.environ.pop("KAERIS_API_KEY", None)
import kaeris  # noqa: E402
from kaeris import cli  # noqa: E402

os.chdir(workdir)
res = {}
for lang in langs:
    buf, ebuf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
        try:
            code = cli.main(["check", "--source", source, "--langs", lang, "--json"])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    out = buf.getvalue()
    try:
        parsed = json.loads(out)
    except ValueError:
        parsed = None
    res[lang] = {"code": code, "result": parsed, "out": None if parsed is not None else
                 (out + ebuf.getvalue())[-600:]}
sys.stdout.write(json.dumps({"using": kaeris.__file__, "version": kaeris.__version__, "res": res},
                            ensure_ascii=False))
