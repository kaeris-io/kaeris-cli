"""Two plain links, never a request: the CLI sends nothing anywhere to print them.

1. When the server refuses a run on a plan limit: one stderr line with the pricing page.
2. After a clean `kaeris check`: a short line on every tenth clean run, and only in a terminal.
   Never in CI, never with --json/--sarif, never when stderr is a pipe or a log file.

Both are off with KAERIS_NO_CTA=1. The links carry ?utm_source=cli: the site reads the source
of a visit from utm_source (it does not read ?ref=). Stdlib only; anything that goes wrong
(unwritable cache, odd file) ends in silence, never in a failed command."""
import json
import os
import re
import sys

PRICING_URL = "https://kaeris.dev/pricing.html?utm_source=cli"
SITE_URL = "https://kaeris.dev/?utm_source=cli"
LIMIT_LINE = f"Limit reached. Plans and limits: {PRICING_URL}"
CHECK_LINE = f"To translate new keys: kaeris translate, or {SITE_URL}"
CHECK_EVERY = 10
_CACHE_FILE = "cta.json"

# The server's own sentences for a refusal on a plan limit (backend/main.py). The per-minute
# rate limit ("still rate-limited") is not one of them: waiting fixes it, a plan does not.
_LIMIT = re.compile(
    r"File exceeds free tier|File exceeds limit|on your plan\)|languages per file|"
    r"Verify meaning works on up to|today's free allowance|free demo is at capacity|"
    r"free tier is at capacity|are left of your|Monthly volume limit reached|"
    r"Webhooks are available on",
    re.IGNORECASE)

_limit_said = False


def disabled(env=None):
    env = os.environ if env is None else env
    return env.get("KAERIS_NO_CTA", "").strip().lower() not in ("", "0", "false", "no")


def retag(message):
    """The API marks its pricing link utm_source=api; printed by this CLI it is the CLI's."""
    return re.sub(r"(kaeris\.dev/[\w./-]*\?utm_source=)api\b", r"\g<1>cli", message or "")


def is_limit(message):
    return bool(_LIMIT.search(message or ""))


def limit_line(message, *, env=None):
    """The line to print after a refused run, or None. Once per process: a run over many
    files that all meet the same wall says it once."""
    global _limit_said
    if _limit_said or disabled(env) or not is_limit(message):
        return None
    if PRICING_URL in retag(message):
        return None  # the server's sentence already carries the link
    _limit_said = True
    return LIMIT_LINE


def _cache_path(env):
    from .updatecheck import cache_dir
    return os.path.join(cache_dir(env), _CACHE_FILE)


def check_line(*, env=None, stream=None, machine=False, ci=False, path=None):
    """The line to print after a clean check, or None. Counts clean runs in a local file and
    answers on every CHECK_EVERY-th one. A machine that cannot keep the count (a fresh CI
    runner, a read-only home) never sees it: the first run is never the tenth."""
    try:
        env = os.environ if env is None else env
        stream = sys.stderr if stream is None else stream
        if machine or ci or env.get("CI") or disabled(env):
            return None
        if not (hasattr(stream, "isatty") and stream.isatty()):
            return None
        path = path or _cache_path(env)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        n = data.get("clean_checks")
        n = (n if isinstance(n, int) and n >= 0 else 0) + 1
        data["clean_checks"] = n
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return CHECK_LINE if n % CHECK_EVERY == 0 else None
    except Exception:
        return None
