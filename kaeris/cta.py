"""Plain lines with a link, never a request: the CLI sends nothing anywhere to print them.

1. When the server refuses a run on a plan limit: one stderr line with the pricing page.
2. After a clean `kaeris check`: a short line on every tenth clean run, and only in a terminal.
3. After a `kaeris check` that found missing keys: one line with the command that fills them,
   about how many characters that is, and which plan covers it (kaeris/plans.py). If the Free
   plan covers it, the line says so. Every such run: it is the fix, like a linter's "--fix".
2 and 3 are never shown in CI, with --json/--sarif/--ci, or when stderr is a pipe or a log file.

All are off with KAERIS_NO_CTA=1. The links carry ?utm_source=cli: the site reads the source
of a visit from utm_source (it does not read ?ref=). Stdlib only; anything that goes wrong
(unwritable cache, odd file) ends in silence, never in a failed command."""
import json
import os
import re
import sys

from . import estimate as est
from .plans import PLANS

PRICING_URL = "https://kaeris.dev/pricing.html?utm_source=cli"
SITE_URL = "https://kaeris.dev/?utm_source=cli"
LIMIT_LINE = f"Limit reached. Plans and limits: {PRICING_URL}"
CHECK_LINE = f"To translate new keys: kaeris translate, or {SITE_URL}"
FIX_URL = PRICING_URL + "&utm_campaign=check-fix"
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
        if _quiet(env, stream, machine, ci):
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


def _quiet(env, stream, machine, ci):
    """True when a line for a person must not be printed: CI, machine output, a pipe, opt-out."""
    if machine or ci or env.get("CI") or disabled(env):
        return True
    return not (hasattr(stream, "isatty") and stream.isatty())


# The plans in the order a growing project meets them. Lifetime has no monthly volume: the
# tokens are paid on the person's own OpenRouter key.
_ORDER = ("free", "pro", "teamapi", "lifetime")
_NAMES = {"free": "Free", "pro": "Pro", "teamapi": "Team/API", "lifetime": "Lifetime"}


def _limits(tier, plans):
    p = plans[tier]
    if tier == "free":  # with a free key: no email, and the only Free with a monthly volume
        return p["month_with_key"], p["file_with_key"]
    return p.get("month"), p["file"]


def gap_units(source_flat, missing, incremental):
    """(characters to translate, the largest single request) for the keys `check` found missing.

    With --only-new (JSON, ARB) a run sends each language's missing keys as its own request;
    every other format is sent whole, one request for all languages, each language charged the
    whole file. Metered the way the server meters a run without verify (kaeris/estimate.py)."""
    whole = sum(len(v) for v in source_flat.values() if isinstance(v, str))
    per_lang = []
    for keys in missing.values():
        if not keys:
            continue
        if incremental:
            n = sum(len(source_flat[k]) for k in keys if isinstance(source_flat.get(k), str))
        else:
            n = whole
        per_lang.append(est.metered(n, 0, False))
    if not per_lang:
        return 0, 0
    return sum(per_lang), (max(per_lang) if incremental else whole)


def fix_command(langs, path=None, out=None, incremental=True):
    """`kaeris translate` for the languages with gaps, as a person would type it."""
    def q(s):
        return f'"{s}"' if re.search(r"[\s&|;<>()$`'\"]", s) else s
    parts = ["kaeris translate"]
    if path:
        parts.append(q(path))
    parts.append("--langs " + ",".join(langs))
    if out:
        parts.append("--out " + q(out))
    if incremental:
        parts.append("--only-new")
    return " ".join(parts)


def fix_text(total, largest, command, *, plans=None, npm=False):
    """The line itself. Pure: the numbers in, the sentence out."""
    plans = PLANS if plans is None else plans
    head = ("Fix with the Python package (pipx install kaeris): " if npm else "Fix: ") + command
    head += f", about {total:,} characters"
    prev = None
    for tier in _ORDER:
        month, file = _limits(tier, plans)
        if (month is None or total <= month) and largest <= file:
            break
        prev = tier
    else:
        _, file = _limits("lifetime", plans)
        return (f"{head}: one request of {largest:,} characters is over the {file:,} per file "
                f"of every plan, split the file. {FIX_URL}")
    if prev is None:
        return f"{head}: within Free ({plans['free']['month_with_key']:,} a month with a free key). {FIX_URL}"
    pmonth, pfile = _limits(prev, plans)
    by_month = pmonth is not None and total > pmonth
    why = (f"over {_NAMES[prev]}'s {pmonth:,} a month" if by_month else
           f"one request of {largest:,} characters is over {_NAMES[prev]}'s {pfile:,} per file")
    life = f"Lifetime ${plans['lifetime']['price']} once with your own OpenRouter key"
    if tier == "lifetime":
        return f"{head}: {why}; {life} has no monthly limit. {FIX_URL}"
    month, file = _limits(tier, plans)
    covers = f"covers {month:,} a month" if by_month else f"takes {file:,} per file"
    return (f"{head}: {why}; {_NAMES[tier]} ${plans[tier]['price']}/month {covers}, "
            f"or {life}. {FIX_URL}")


def fix_line(total, largest, command, *, env=None, stream=None, machine=False, ci=False):
    """The line to print after a check that found missing keys, or None."""
    try:
        env = os.environ if env is None else env
        stream = sys.stderr if stream is None else stream
        if total <= 0 or _quiet(env, stream, machine, ci):
            return None
        return fix_text(total, largest, command)
    except Exception:
        return None
