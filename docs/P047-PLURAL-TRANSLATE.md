# 0.2.47 candidate: `kaeris translate` writes every plural form `kaeris check` asks for

Found at acceptance round 3 (21.11): `kaeris translate` 0.2.46 wrote the Polish few/many forms
for an ICU plural, but not for an i18next `_one/_other` set or a nested `one/other` object, and
its own `kaeris check` then failed (i18next) or warned (nested). Raw output of that run:
i18n_tool `p23-docs-inputs-1119:docs/p23/checks/round3/translate-writes-plural-forms-0.2.46*.txt`.

## Reproduced on d5535f0 (CLI) + 94114a89 (server `night/redesign-2026-10`)

Local server, stub model (`OPENROUTER_URL` pointed at an offline stand-in that writes the full
CLDR forms for an ICU plural, as the real model did in round 3), $0. `translate` then `check`
per language:

| source shape | pl | ru | ar | ja |
|---|---|---|---|---|
| i18next `items_one/items_other` (flat and inside a namespace) | RED | RED | RED | green |
| nested JSON `items.one/items.other` | WARN | WARN | WARN | green |
| YAML (Rails) `items: one/other` | WARN | WARN | WARN | green |
| ICU in JSON, ARB, xcstrings, Android `<plurals>`, Fluent, `.po` nplurals, i18next ordinals | green | green | green | green |

`--only-new` (the GitHub Action's mode) on a target that already has `items_one/items_other`:
"up to date", `check` stays red — the missing forms are not seen as work.

Welsh (`cy`) is not one of the 46 languages the server translates: `translate --langs cy` is
refused before anything is sent (`Unknown language code: cy`). Its forms are covered by unit tests
of the server code (the same `_CLDR_REQUIRED` row), not by a translate run.

## Where the forms are made

On the server (`backend/translator.py`). The CLI sends the file and writes what comes back.
ICU, ARB, xcstrings, Android and Fluent work because the plural reaches the model as ONE ICU
string: Android and Fluent are folded into one (`_fold_plurals`, audit D3 25.10), sent, repaired
if a form is missing (`_repair_plurals`), and unfolded into the TARGET language's categories
(`_unfold_plurals`). i18next suffixes and nested objects were never folded: to the model
`items_one` and `items_other` are two unrelated strings, and no step adds `items_few`.

The CLI has one more gap of its own, in `--only-new`: a plural set counts as up to date when its
source keys are present, and a form the server adds (`cart.items_few`) is merged as a top-level
key literally named `"cart.items_few"` (`incremental.merge_translation` puts unknown keys at the
root).

## Plan

Server, branch `plural-translate-1121` of i18n_tool (from `night/redesign-2026-10`):

1. `_fold_plurals`: fold JSON/YAML/ARB plural sets (formats `json`, `json-flat`, `yaml`,
   `yaml-flat`, `yaml-rooted`, `arb`) into one ICU string. A set is found exactly as
   `kaeris check` finds it (`check._plural_sets`): `base_<cat>` keys with both `_one` and
   `_other`; or an object whose direct children are all CLDR categories, with `one` and `other`.
   An i18next ordinal set (`base_ordinal_*`) is NOT folded: check has no ordinal table and owes
   only `_ordinal_other`, which every form translated on its own already gives.
2. `_unfold_plurals` for these formats: the categories written are the source's own plus what
   `_CLDR_REQUIRED` (the table `check` reads, parity-tested against `detectors._CLDR_REQUIRED`)
   requires for the target, so the result is exactly what `check` asks for: nothing missing and
   no form `check` would call stale. A language with one form (ja) gets the `other` text in every
   source key (`items_one` stays, so `--only-new` does not re-send it every run; i18next never
   reads `_one` there). `#` from the model becomes the set's own count placeholder (`{{count}}`,
   `%{count}`, `{count}`).
3. Project memory: a folded set whose members are all reused AND whose source already has every
   form the target needs is reused as one ICU string (German keeps its free reuse); otherwise the
   set is translated again (Polish: the memory has no `_few`).
4. `_plural_gaps` names a JSON set by its base (`items`), not `items_`.
5. Tests: `backend/tests/test_json_plurals_get_every_form.py` — real `translate_file`, model
   stubbed, ZIP parsed back: pl/ru/ar/cy/ja/de for i18next, nested JSON, namespaced i18next,
   YAML; ordinal set untouched; repair fills a short answer; reuse rule of step 3. Seen failing
   on the unmodified code first.

CLI, branch `plural-translate-1121` of kaeris-cli (from `release-0.2.46-pluralwarn`, d5535f0):

6. `--only-new`: a plural set is work when any of its keys is, and when the target lacks a form
   the target language needs (same tables as `check`, via `check._plural_sets` /
   `check._language_forms`); the whole set is sent, so the server can fold it.
7. `incremental.merge_translation`: a form the source does not have (`items_few`,
   `items.few`) lands beside its `other` sibling, not at the root.
8. Parity: `tests/test_detector_parity.py` gains a check that the server's set finder returns the
   same sets as `check._plural_sets` (runs in the server CI, which clones the same-named branch).
9. Tests: `tests/test_translate_completes_plural_sets.py` (only-new todo + merge), seen failing
   first.
10. Full suites: CLI py and npm; i18n_tool pytest in 4 groups.

Not in scope, written down: `.po` slots beyond the source's two get a copy of the plural form
(Polish msgstr[2] = msgstr[1]) — `check` is green (nplurals is right) but the words are the
`few` form; folding `.po` the same way is the next step (server `_PO_SLOT_CATS` already maps
slots to categories). Ordinal categories of the target (cy needs six) are not added for the same
reason `check` does not ask for them: no ordinal table. `.stringsdict` is not a supported format.

## vs the leaders (missing plural forms when machine-translating)

From the vendors' documentation (21.11, web; nothing run, no accounts):

| tool | a target that needs more forms than the source (en one/other -> pl, ar) | KAERIS 0.2.47 |
|---|---|---|
| i18next-cli `extract`/`sync` | can write the target's extra suffix keys (`allPluralForms`, "English ... also gets _few/_many (needed by Polish)"); value = `defaultValue`, `''` in the README example; no translation. i18next suffixes only | writes the extra keys translated, i18next + nested + YAML + ICU + Android + Fluent + xcstrings |
| Lingo.dev CLI | not documented on lingo.dev/cli (plurals appear only in the separate React SDK docs); unverified | |
| Crowdin | the i18next JSON file type splits a plural into the target's forms in the editor; what MT pre-translation puts into forms the source lacks is not documented; i18next ordinals not supported | ordinals keep `_ordinal_other` (what `check` owes) |
| Lokalise | target forms are created by Unicode rules; standard MT in automations fills only the forms the source has, the others stay EMPTY; Lokalise AI (Pro) can generate all target forms | every required form, standard plan, verified by `check` in CI |

Sources: github.com/i18next/i18next-cli (README: `allPluralForms`, `defaultValue`,
`sync --changed-only`); lingo.dev/en/cli; store.crowdin.com/i18next-json,
community.crowdin.com/t/i18next-custom-language-ordinal-support/7883;
docs.lokalise.com/en/articles/1400503-plurals.
