"""kaeris check — the "i18n firewall": a local, static comparison of a source
(base-language) locale file against each target locale file.

Pure stdlib, no network/API call. Designed to run in CI and fail the build
(non-zero exit) when a locale is untranslated or a translated string lost/
gained a placeholder — the kind of bug that silently breaks the app at
runtime (`Hello {name}` -> `Bonjour` drops the name; `{name}` -> `{nom}`
just crashes str.format()/ICU).

Every format `translate` writes goes through the same comparison: a reader (kaeris/formats.py)
turns the file into {key: text}, and everything below works on those.
"""

import json
import re

from .incremental import flatten_all
from . import detectors as det
from . import glossary as gl
from . import ftl
from .formats import lone_count_to_hash

# Percent/dollar-style placeholders (order matters: positional and %@ must be
# tried before the bare %s/%d/... class since e.g. "%1$s" would otherwise
# partially match the bare-conversion alternative first).
_PERCENT_RE = re.compile(r"%\d+\$[@a-zA-Z]|%@|%[sdifxocegpnXOCEGP%]")
# ${name} template-literal placeholders. Scanned (and masked) BEFORE the brace
# scanner so a ${x} span isn't also miscounted as a bare {x} — they're distinct
# families: a source ${name} translated to {name} would break at runtime, and
# that mismatch must be caught. (Previously the brace scanner masked ${name}
# down to {name} before this ran, making the regex dead — M2.)
_DOLLAR_RE = re.compile(r"\$\{[\w\d]+\}")
# NOTE: a :word: (colon on both sides) "family" was removed here (M1). It never
# matched the real Rails/Laravel `:name` convention (leading colon only) and it
# false-positived on emoji shortcodes / prose like ":smile:" — failing CI on a
# non-placeholder. No format currently in the pipeline (i18next, next-intl,
# react-intl, vue-i18n, flutter-arb, JSON/percent) relies on a colon placeholder,
# so it's dropped rather than replaced with a leading-colon regex that would
# itself misfire on ordinary text (times "12:30", ratios "3:2").


def _brace_spans(text):
    """Balanced top-level {...} spans in `text`. Covers plain named
    placeholders ({name}), doubled/i18next-style ({{name}}), and ICU
    MessageFormat ({count, plural, one {# item} other {# items}}) as a
    single opaque span each — nested braces don't confuse it."""
    spans = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "{":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                spans.append((i, j))
                i = j
                continue
        i += 1
    return spans


def _brace_identity(span_text):
    """Reduce a brace span to a comparable identity: strip doubled braces
    and any ICU plural/select clause, keeping just the argument name, so
    '{{name}}' -> '{name}' and '{count, plural, one {..} other {..}}' -> '{count}'.
    This intentionally ignores ICU sub-clause wording (which legitimately
    differs per language, e.g. Slavic plural categories) — only the bound
    variable name has to match between source and target."""
    inner = span_text.strip("{}")
    while inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    name = inner.split(",")[0].strip()
    return "{" + name + "}"


def find_placeholders(text):
    """Return the set of placeholder identities found in a string."""
    if not isinstance(text, str):
        return set()
    found = set()
    chars = list(text)
    # 1) ${name} template placeholders first — mask each span so the { } inside
    #    isn't also miscounted as a bare {name} brace placeholder (distinct family).
    for m in _DOLLAR_RE.finditer(text):
        found.add(m.group(0))
        for i in range(m.start(), m.end()):
            chars[i] = " "
    masked = "".join(chars)
    # 2) Balanced {...} brace spans (plain/doubled/ICU) on the ${}-masked text.
    spans = _brace_spans(masked)
    found.update(_brace_identity(masked[s:e]) for s, e in spans)
    # 3) Mask brace regions too so percent scanning can't double-count them.
    for s, e in spans:
        for i in range(s, e):
            chars[i] = " "
    remainder = "".join(chars)
    found.update(_PERCENT_RE.findall(remainder))
    return found


# A .po plural has msgstr[0], [1] and, for languages with more forms, [2]... Only the first two
# have a counterpart in the source; the rest are read against its plural form, never reported
# as extra keys.
_EXTRA_FORM_RE = re.compile(r"⟦plural:\d+⟧$")


def source_twin(key, source_flat):
    """The source key this target key is compared against: itself, or for an extra plural form
    the source's plural form. None when there is none."""
    if key in source_flat:
        return key
    twin = _EXTRA_FORM_RE.sub("⟦plural⟧", key)
    return twin if twin != key and twin in source_flat else None


def _pairs(source_flat, target_flat, optional=()):
    """(key, source value, target value) for every key both sides have, in the source's order,
    then the extra plural forms the target has. For the keys in `optional` (a .po singular
    form) a lone count is read as `#` on both sides: "Eine Datei" is a correct "%d file"."""
    for key, src_val in source_flat.items():
        if key in target_flat:
            tgt_val = target_flat[key]
            if key in optional and isinstance(src_val, str) and isinstance(tgt_val, str):
                src_val, tgt_val = lone_count_to_hash(src_val), lone_count_to_hash(tgt_val)
            yield key, src_val, tgt_val
    for key, tgt_val in target_flat.items():
        twin = source_twin(key, source_flat)
        if twin is not None and twin != key:
            src_val = source_flat[twin]
            if key in optional and isinstance(src_val, str) and isinstance(tgt_val, str):
                src_val, tgt_val = lone_count_to_hash(src_val), lone_count_to_hash(tgt_val)
            yield key, src_val, tgt_val


def diff_locale(source_flat, target_flat, pair=True, optional=()):
    """Compare one target locale's flattened keys against the flattened source.

    Returns (missing, extra, placeholder_issues):
      - missing: sorted dotted keys present in source but absent from target
      - extra: sorted dotted keys present in target but absent from source
      - placeholder_issues: list of {"key", "missing", "added"} dicts, where
        "missing" = placeholders present in source but lost in target, and
        "added" = placeholders present in target but not in source (renamed
        or hallucinated) — either one means the string will misbehave/crash
        at runtime.
    """
    missing = sorted(k for k in source_flat if k not in target_flat)
    extra = sorted(k for k in target_flat if source_twin(k, source_flat) is None)

    issues = []
    if not pair:
        return missing, extra, issues
    for key, src_val, tgt_val in _pairs(source_flat, target_flat, optional):
        if not isinstance(src_val, str) or not isinstance(tgt_val, str):
            continue
        if not src_val.strip():
            continue                    # an empty source has nothing to compare against
        src_ph = find_placeholders(src_val)
        tgt_ph = find_placeholders(tgt_val)
        if src_ph != tgt_ph:
            issues.append({
                "key": key,
                "missing": sorted(src_ph - tgt_ph),
                "added": sorted(tgt_ph - src_ph),
            })
    return missing, extra, issues


CLDR_ORDER_LOCAL = ("zero", "one", "two", "few", "many", "other")
_CATS = "zero|one|two|few|many|other"
# i18next v4 suffixes (`item_one`, `item_few`). The Rails / nested-object shape (`items.one`,
# `items.other`) is found by its parent instead: see _plural_sets.
_I18N_SUFFIX_RE = re.compile(rf"^(.+)_({_CATS})$")
# i18next writes ordinals as `place_ordinal_one`. Their categories are not the cardinal ones
# (Polish and Russian ordinals have `other` alone, English has one/two/few/other), and there
# is no ordinal table here, so an ordinal set is never held to cardinal forms.
_ORDINAL = "_ordinal"
_PLURAL_KEY = "⟦plural⟧"


def _plural_sets(source_flat):
    """{(base, separator): forms} for every plural set of the source. An i18next set needs both
    `_one` and `_other`, so a lone `thing_other` is not taken for one. A dotted set needs both
    too, and every key under its base must be a CLDR category: `{one, other, title}` is an
    object that happens to have a key `one`, not a plural."""
    sets, children = {}, {}
    for key in source_flat:
        m = _I18N_SUFFIX_RE.match(key)
        if m:
            sets.setdefault((m.group(1), "_"), set()).add(m.group(2))
        head, dot, leaf = key.rpartition(".")
        if dot:
            children.setdefault(head, set()).add(leaf)
    nested = set()                      # bases with something deeper than a direct child
    for key in source_flat:
        parts = key.split(".")
        nested.update(".".join(parts[:i]) for i in range(1, len(parts) - 1))
    for head, leaves in children.items():
        if leaves <= set(CLDR_ORDER_LOCAL) and head not in nested:
            sets[(head, ".")] = set(leaves)
    return {s: f for s, f in sets.items() if {"one", "other"} <= f}


def _language_forms(lang):
    """(forms the language must have, or None when not known; True if `other` is all it has)."""
    base_lang = (lang or "").replace("_", "-").split("-")[0].lower()
    if base_lang in det._NO_SINGULAR:
        return {"other"}, True
    required = det._CLDR_REQUIRED.get(base_lang)
    return (required | {"other"} if required else None), False


def plural_set_work(source_flat, target_flat, todo, lang, complete=True, incomplete=None):
    """({key: source text}, {key: source text}) of the plural sets `translate --only-new` must
    send WHOLE, beyond `todo`: (1) a set one of whose keys is in `todo`, (2) a set the target
    lacks a form of that `lang` needs (the forms this module asks for: a Polish file with
    `items_one/items_other` only is not up to date).

    Only where sending the whole set buys a form (round 5: new behaviour only where it is
    plainly right, else what 0.2.46 sent):
      - `complete`: the server adds forms (it says so in /api/config); one that does not would
        get the set, and charge it, on every run;
      - `lang` needs a form the set's source lacks (Polish few/many; never German, never a
        one-form language): elsewhere an edited form goes alone, as 0.2.46 sent it;
      - the server folds the set (plural_set_foldable): one it leaves as it is never gets a form;
      - (2) only: the set is not in `incomplete` with its current source ({set id: hash} from
        kaeris.lock, plural_incomplete_marks): sent whole once already, the server did not add
        every form, and nothing changed since (critic round 4, B7: charged on every run).
    Ordinal sets owe only `_ordinal_other` and are translated form by form: never added."""
    forms, single = _language_forms(lang)
    need = set() if single or not forms else forms
    with_todo, to_complete = {}, {}
    if not complete or not need:
        return with_todo, to_complete
    for (base, sep), src_forms in _plural_sets(source_flat).items():
        if sep == "_" and base.endswith(_ORDINAL):
            continue
        if not need - set(src_forms):
            continue                    # the source has every form: nothing to add
        keys = [f"{base}{sep}{c}" for c in CLDR_ORDER_LOCAL if c in src_forms]
        if not plural_set_foldable({k: source_flat[k] for k in keys}):
            continue
        rest = {k: source_flat[k] for k in keys if k not in todo}
        if any(k in todo for k in keys):
            with_todo.update(rest)
        elif any(f"{base}{sep}{c}" not in target_flat for c in need) and                 (incomplete or {}).get(f"{base}{sep}") != _set_hash(source_flat, keys):
            to_complete.update(rest)
    return with_todo, to_complete


# What the server reads as an ICU block inside a form (translator._ICU_HEAD_RE).
_ICU_HEAD_RE = re.compile(r"\{\s*[\w\d_]+\s*,\s*(plural|selectordinal|select)\s*,")


def plural_set_foldable(forms):
    """Whether the server folds this set into one ICU string (translator._fold_plurals, JSON/
    YAML/ARB): every form plain text with balanced braces, none holding an ICU block, none with
    a `#` of its own (that `#` could not be told from ICU's number). A set it does not fold is
    translated key by key and never gets a new form, so `--only-new` does not send it to be
    completed. tests/test_detector_parity.py holds this to the server's own fold."""
    texts = list(forms.values())
    if not texts or not all(isinstance(t, str) for t in texts):
        return False
    for t in texts:
        if "#" in t or _ICU_HEAD_RE.search(t):
            return False
        depth = 0
        for ch in t:
            depth += ch == "{"
            depth -= ch == "}"
            if depth < 0:
                return False
        if depth:
            return False
    return True


def _set_hash(source_flat, keys):
    import hashlib
    body = json.dumps({k: source_flat.get(k) for k in sorted(keys)}, ensure_ascii=False,
                      sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def plural_incomplete_marks(source_flat, target_flat, lang, sent):
    """{set id: hash of its source forms} of the sets with a key in `sent` that the target still
    lacks a `lang` form of after the run: the server did not complete them. kaeris.lock keeps
    these (`plural_incomplete`) so that plural_set_work does not send them again to be completed
    until their source changes."""
    forms, single = _language_forms(lang)
    need = set() if single or not forms else forms
    marks = {}
    for (base, sep), src_forms in _plural_sets(source_flat).items():
        keys = [f"{base}{sep}{c}" for c in CLDR_ORDER_LOCAL if c in src_forms]
        if not any(k in sent for k in keys):
            continue
        if any(f"{base}{sep}{c}" not in target_flat for c in need):
            marks[f"{base}{sep}"] = _set_hash(source_flat, keys)
    return marks


def plural_keys_translated_again(source_flat, lang):
    """The keys of the plural sets a server with `plural_forms` translates again whatever the
    project memory holds: a set the target needs a form of that its source lacks (Polish few and
    many for `items_one/items_other`). The memory has only the source's forms, so the server
    cannot reuse the set as a whole (its `_fold_reuse`), and the CLI must not count those lines
    as remembered."""
    forms, single = _language_forms(lang)
    if single or not forms:
        return set()
    keys = set()
    for (base, sep), src_forms in _plural_sets(source_flat).items():
        if sep == "_" and base.endswith(_ORDINAL):
            continue
        if forms - set(src_forms):
            keys.update(f"{base}{sep}{c}" for c in src_forms)
    return keys


def _plural_set_faults(source_flat, target_flat, missing, extra, lang):
    """(faults, missing, extra) once every plural set is read by the TARGET language's forms.

    A Polish `item_one`/`item_other` pair is incomplete: CLDR gives Polish one/few/many/other,
    so `item_few` and `item_many` are required — and not "stale" when present. Japanese has
    `other` alone, so a Japanese file without `item_one` is complete, not missing a key
    (i18next itself never reads `_one` for Japanese). The same holds for Rails `items.one`, for
    a .po plural whose header has one form (msgstr[0] only), and for i18next ordinals, which
    owe only `_ordinal_other`. Languages outside det._CLDR_REQUIRED / det._NO_SINGULAR are not
    judged: the same conservative tables the ICU check uses.

    Each fault is (msg, severity). 0.2.43 judged i18next `_` sets in its own table only, so a
    dotted (Rails) set and a Welsh set are WARN: they fail only with --strict (variant B)."""
    base_lang = (lang or "").replace("_", "-").split("-")[0].lower()
    forms, single = _language_forms(lang)
    faults, owned, optional = [], set(), set()
    for (base, sep), src_forms in sorted(_plural_sets(source_flat).items()):
        other = f"{base}{sep}other"
        if sep == "_" and base.endswith(_ORDINAL):
            if other in target_flat:
                optional.update(f"{base}{sep}{c}" for c in src_forms)
            continue
        if single and other in target_flat:
            optional.update(f"{base}{sep}{c}" for c in src_forms)
        if not forms:
            continue
        old = sep == "_" and base_lang in det._PLURAL_RED_SINCE_043
        for cat in sorted(forms):
            key = f"{base}{sep}{cat}"
            owned.add(key)
            if key not in source_flat and key not in target_flat:
                faults.append((f"plural form missing: {key} — {base_lang} needs the "
                               f"{'/'.join(c for c in CLDR_ORDER_LOCAL if c in forms)} forms of '{base}'",
                               det.ERROR if old else det.WARN))
    if single:
        # gettext: msgid_plural is the second form, and a one-form language has no second.
        optional.update(k for k in missing if k.endswith(_PLURAL_KEY)
                        and k[:-len(_PLURAL_KEY)] in target_flat)
    return (faults, [k for k in missing if k not in optional],
            [k for k in extra if k not in owned])


def plural_set_faults(source_flat, target_flat, missing, extra, lang):
    """The public name of _plural_set_faults (0.2.47), for kaeris-mcp: after diff_locale, read the
    plural sets by the TARGET language's CLDR forms, exactly as `kaeris check` does. Without it
    a Polish `items_few` that translate now writes is an "extra/stale" key an agent may delete."""
    return _plural_set_faults(source_flat, target_flat, missing, extra, lang)


def check_locales(source_obj, langs, load_target, glossary=None, terms=None):
    """Run the check across every target language.

    `load_target(lang)` -> the parsed locale for that language (a JSON object, or the flat
    {key: text} a format reader returns), or None if the file doesn't exist (a whole-locale-
    missing lang is reported as every source key being missing). A reader's `notes` (findings
    about the file as a whole, e.g. a .po header that declares too few plural forms) are added
    to the faults/warnings of that language; `skip_pairwise` says the strings cannot be paired
    with the source's by key, so only missing/extra keys are compared.

    Returns the result dict (this is exactly what --json prints):
      {"ok": bool, "missing": {lang: [keys]}, "extra": {lang: [keys]},
       "placeholder_issues": [{"lang", "key", "missing", "added"}],
       "missing_files": [lang, ...],
       "faults": [{"lang", "key", "severity": "error", "msg"}],
       "warnings": [{"lang", "key"?, "severity": "warn", "msg"}]}
    `terms` are the entries of kaeris-glossary.json (kaeris/glossary.py): a term of the source
    must come out as the agreed word of each language.

    `ok` is True only if there are no missing keys, no placeholder issues and
    no RED detector faults (extra/stale keys, empty translations and YELLOW warnings never affect
    `ok` — that's what --strict is for).
    """
    source_flat = flatten_all(source_obj)
    optional = getattr(source_obj, "count_optional", ())

    result = {
        "ok": True,
        "missing": {},
        "extra": {},
        "placeholder_issues": [],
        "missing_files": [],
        "faults": [],
        "warnings": [],
    }

    for lang in langs:
        target_obj = load_target(lang)
        if target_obj is None:
            result["missing_files"].append(lang)
            result["missing"][lang] = sorted(source_flat)
            result["ok"] = False
            continue
        target_flat = ftl.fold_single_form(source_flat, flatten_all(target_obj))
        pair = not getattr(target_obj, "skip_pairwise", False)
        # A .po target adds the slots its own Plural-Forms gives a single number (formats.read_po).
        lang_optional = set(optional) | set(getattr(target_obj, "count_optional", ()))
        for note in getattr(target_obj, "notes", []):
            rec = {"lang": lang, "key": note.get("key", ""), "msg": note["msg"]}
            if note.get("severity") == "error":
                result["faults"].append({**rec, "severity": "error"})
                result["ok"] = False
            else:
                result["warnings"].append({**rec, "severity": "warn"})
        missing, extra, issues = diff_locale(source_flat, target_flat, pair, lang_optional)
        plural_faults, missing, extra = _plural_set_faults(source_flat, target_flat, missing,
                                                           extra, lang)
        if missing:
            result["missing"][lang] = missing
            result["ok"] = False
        for msg, severity in plural_faults:
            if severity == det.ERROR:
                result["faults"].append({"lang": lang, "key": "", "msg": msg, "severity": "error"})
                result["ok"] = False
            else:
                result["warnings"].append({"lang": lang, "key": "", "msg": msg, "severity": "warn"})
        if extra:
            result["extra"][lang] = extra
        for issue in issues:
            result["placeholder_issues"].append({"lang": lang, **issue})
        if issues:
            result["ok"] = False
        # Per-string detectors on shared keys (RED faults + YELLOW warnings).
        for key, src_val, tgt_val in (_pairs(source_flat, target_flat, lang_optional) if pair else ()):
            if not isinstance(src_val, str) or not isinstance(tgt_val, str):
                continue
            if src_val.strip() and not tgt_val.strip():
                result["warnings"].append({"lang": lang, "key": key, "severity": "warn",
                                           "msg": "empty translation — the source has text"})
                continue
            for f in det.string_faults(src_val, tgt_val, lang, glossary) + \
                    gl.faults(src_val, tgt_val, lang, terms):
                rec = {"lang": lang, "key": key, "msg": f["msg"]}
                if f["severity"] == det.ERROR:
                    result["faults"].append({**rec, "severity": "error"})
                    result["ok"] = False
                else:
                    result["warnings"].append({**rec, "severity": "warn"})
        # File-level detectors (overflow / register / consistency) — YELLOW.
        # Same contract as the per-string loop above: the detectors read text, and a locale
        # legitimately holds numbers, booleans, lists and nulls (`translate` carries them
        # through untouched, so our own output has them). Guarding only the per-string loop
        # left `_register_faults` joining a dict with an int in it — a traceback instead of a
        # verdict, and only in languages that have T–V markers (de/fr/es/it/ru).
        src_text = {k: v for k, v in source_flat.items() if isinstance(v, str)}
        tgt_text = {k: v for k, v in target_flat.items() if isinstance(v, str)}
        for f in (det.file_faults(src_text, tgt_text, lang) if pair else ()):
            result["warnings"].append({"lang": lang, "msg": f["msg"], "severity": "warn"})

    return result

