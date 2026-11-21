"""run_cli.py <cli-tree> <args...>: the kaeris CLI from a source tree, whatever kaeris is installed.

PYTHONPATH alone is not enough on this machine: an installed kaeris (the i18n_tool .venv, an
editable install, or a `kaeris/` folder in the current directory) can win the import. The tree
goes first on sys.path, every kaeris module already imported is dropped, and the file that
answers is printed to stderr on every call.
"""
import runpy
import sys

tree = sys.argv[1]
sys.path.insert(0, tree)
for name in list(sys.modules):
    if name == "kaeris" or name.startswith("kaeris."):
        del sys.modules[name]
import kaeris  # noqa: E402

print("using", kaeris.__file__, kaeris.__version__, file=sys.stderr)
if "--which" in sys.argv[2:3]:
    sys.exit(0)
sys.argv = ["kaeris"] + sys.argv[2:]
runpy.run_module("kaeris", run_name="__main__", alter_sys=True)
