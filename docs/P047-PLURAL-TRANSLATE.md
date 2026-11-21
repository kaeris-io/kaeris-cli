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
   no form `check` would call stale. ~~A language with one form (ja) gets the `other` text in every
   source key~~ (round 2, B1: that invented `{{count}}` under `msg_one` "One message from
   {{name}}"; a one-form language now gets the set's keys translated one by one, not folded).
   `#` from the model becomes the set's own count placeholder (`{{count}}`,
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

## Result (21.11)

Branches `plural-translate-1121` in both repos. Server: 5b43274f (test, red: 10 failed / 4
passed on 94114a89, `docs/p047/server-test-red-94114a89.txt` there), cc4b3c09 (fix), 72d90db9
(the accepted variant-B server patch carried along, so detector-parity against this branch can
pass; drop it if the server release brings that patch another way), 9826f884 (a broken answer
is named in QA). Parity locally (CLI tests beside this backend, `KAERIS_BACKEND` set):
detector/encoding/xcstrings/formats parity 47 passed, nothing skipped. CLI: 9d0b67f (test, red: 4 failed / 2 passed on d5535f0, `docs/p047/cli-test-red-d5535f0.txt`),
63319ec (fix), 5655796 (parity test).

`translate` -> `check`, same local stub run as above (`docs/p047/e2e-before-d5535f0-94114a89.txt`
vs `docs/p047/e2e-after.txt`, harness in `docs/p047/harness/`), py and npm, 11 source shapes,
pl/ru/ar/ja, plus `--only-new` twice on targets cut back to one/other: **64/100 green before,
100/100 after**; the second `--only-new` run is "up to date". Welsh: refused by the server in
both (not one of its languages).

Left as it is, on purpose:
- ~~`.po` slots past the source's two are a copy of the plural form~~ — done in step 2 below.
- With project memory, a Polish/Russian/Arabic plural set is translated again on every full run
  (the memory holds only the source's forms; German and Japanese sets are reused). ~~The CLI line
  "N of them come from the project memory" still counts those members.~~ Round 2: it no longer
  does (`cli._without_retranslated`).
- `--only-new` merges a new form at the end of its object (`items_few` after `title` in a flat
  file); the file is valid, only the order differs from a full run.
- ~~A model answer that is no longer one plural keeps the source forms (Android's rule since D3),
  and the run's QA names it in every language (server 9826f884).~~ Round 2: a JSON set or `.po`
  entry whose answer broke is translated form by form, as before 0.2.47 (Android and Fluent keep
  their D3 rule).

## Step 2: `.po` plural slots (21.11)

### Reproduced on 0e3eb54 (CLI) + 8a6b41cd (server)

Same harness, `po` and a new `po-multi` case (POT-style empty msgstr, two `msgctxt` twins, a
singular without the number, a `%s` count), and a new slot check: every plural entry has as many
`msgstr` as the header's `nplurals`, each slot its own form, the singular in the `one` slot,
Japanese's single slot = the plural form. The stub gives every category its own word.
`docs/p047/e2e-po-before-0e3eb54-8a6b41cd.txt`: `check` GREEN on all 16 runs, slot check RED on
all 24:

- pl/ru: `msgstr[2]` = `msgstr[1]` (the `few` word stands for `many`);
- ar: `msgstr[0]` (zero) holds the singular, `msgstr[1]` (one) and 2..5 the English plural form;
- ja: the one slot holds the singular, not the `other` form.

`--only-new` on `.po`: the CLI warns "JSON/ARB only" and translates the whole file; the result is
byte-identical to the full run (so the same wrong slots). The project memory is not used for
`.po` (the CLI builds its lookup only from JSON/ARB), so nothing is reused there either.

Cause: `_parse_po` gives a plural entry two flat keys (`msgid`, `msgid\x01`), the model
translates them as two unrelated strings, and `_serialize_po` writes `s0` into slot 0 and `s1`
into every slot from 1 on — whatever category the target's Plural-Forms numbers them as.

### Plan (server `backend/translator.py`; the CLI needs no code change)

1. `_fold_plurals(flat, "po", passthrough)`: for every plural entry of `__po__.entries` fold its
   source forms into one ICU string under `<msgid key>` + `_FOLD_MARK`. Source forms: slot 0 and
   1 from `flat`, slots 2.. from `src_strs` (a translated ru/pl source); their categories from
   `_po_slot_cats` (the existing `_PO_SLOT_CATS` table) by the source's Language, `en` for a POT;
   `other` = the last slot when the language has none (pl `one/few/many`). Not folded, as before:
   a form that already holds an ICU block, unbalanced braces, an unknown 3+-slot language.
2. `_unfold_plurals` for `po`: target slots = `_po_slot_cats(lang, nplurals of _plural_rule_for(lang))`;
   slot i = the answer's arm for that category, else its `other` arm. Slot 0 -> the msgid key,
   slot 1 -> the `\x01` key, slot i>=2 -> a new key `<\x01 key>\x01<i>` (`_po_slot_key`). ja/zh/ko:
   one slot = `other`. `#` -> the entry's own count placeholder (`%d`, `%s`, `{n}`), as for JSON.
   An answer that is no longer one plural keeps the source forms (old output).
3. `_serialize_po`: slot i>=2 reads `_po_slot_key` first, then the same-language source slot,
   then the old copy of slot 1. Header logic unchanged (already the target's Plural-Forms).
4. The run's bookkeeping: warnings/scores of the folded key move to the entry's exact keys (not
   a prefix match: `File` is a prefix of `Files`); `_plural_gaps` names an entry whose answer
   broke by its msgid; `_fold_reuse` reuses a remembered entry only when every target slot is
   remembered (de: slots 0/1; pl needs slot 2 too).
5. Test `backend/tests/test_po_plurals_get_every_form.py`: real `translate_file` + ZIP, stub model
   answers every category with its own word; expected order read from `_PO_SLOT_CATS`, categories
   from `_CLDR_REQUIRED`; pl, ru, uk, cs, ar each slot its own form; ja/zh/ko one slot = `other`;
   Plural-Forms of the target; msgctxt twins; `#`; broken answer; reuse rule. Seen red first.
6. e2e (this harness) py + npm, all cases; CLI full suites py + npm; server pytest 4 groups,
   failing ids vs 94114a89.

Found by the e2e after steps 1-5 (server 8a8177ba, `docs/p047/harness` run `e2e-po-after`): all
slots right, but `kaeris check --langs ar` RED on `po-multi` (py and npm): "One message (ctx
mail, plural): lost placeholder %d". `check` reads msgstr[1] against msgid_plural, and Arabic's
msgstr[1] is the `one` slot: "رسالة واحدة" is correct without the number. Before, that slot held
the English plural with `%d`, so it never showed. The rule chosen: a slot the Plural-Forms
formula picks for exactly ONE n in 0..1000 may leave the number out (Arabic zero/one/two = 0,
1, 2; Polish/Czech one = 1; Hebrew one/two). This is NOT "as `msgfmt -c`" (the first wording
here said so; critic 21.11): gettext lets a slot go when the formula picks it for fewer than 5
values of n, so KAERIS is stricter on Czech/Slovak few (2-4), Irish slots 2/3 and Scottish
Gaelic slot 1; and since round 2 KAERIS trusts the formula only when it is sound and the
language's own, where msgfmt takes any formula that stays below nplurals (round 2, B2). CLI,
both ports:

7. `formats.read_po` (target): evaluate the file's own `plural=` expression (a small C-expression
   evaluator, no table) for n = 0..1000; the slots hit by exactly one n join `count_optional`
   (msgstr[0] already is). `check`: the target's `count_optional` joins the source's, and
   `_pairs` applies it to the extra slots (`⟦plural:N⟧`) too. A slot that covers many numbers
   (pl `many`, ru `one` past slot 0) still must keep the number.
8. Tests: `tests/test_po_single_number_slots.py` (ar one/two without the number green; ar many
   without it red; pl few without it red; evaluator on every `_PLURAL_RULES` formula), seen red
   first; npm parity corpus cases + baselines regenerated (`npm/test/gen_baselines.py --write`).

### Result (21.11)

Server: bcd325e5 (test, red: 14 failed / 1 passed on 8a6b41cd,
`docs/p047/server-po-test-red-8a6b41cd.txt` there), 8a8177ba (fix; with the JSON plural and
.po convert tests 48 passed, `server-po-test-green.txt`). CLI: de076ca (repro), a283e55 (test,
red: 4 failed / 3 passed, `docs/p047/cli-po-slots-test-red-387fb1e.txt`), c908630 (check fix,
py + npm; the existing 294 npm baselines unchanged, 5 new), parity against this server 48
passed, nothing skipped (the new one: every server Plural-Forms parses and its loose slots are
`zero/one/two` in `_PO_SLOT_CATS`).

e2e `docs/p047/e2e-po-after.txt` (cli c908630 + server 8a8177ba): **134/134 green** — the 100
earlier rows (all formats, py + npm, `--only-new` on JSON) plus `po-multi` check rows, the slot
check on every `.po` target (pl/ru each slot its own word, ar six in zero..other order with the
singular in msgstr[1], ja one slot = the plural form), and `--only-new` on `.po` (whole file,
byte-identical, slots right). Before: `docs/p047/e2e-po-before-0e3eb54-8a6b41cd.txt`, 18/42.

Full suites: CLI py 869 passed (36 skipped, all structural), npm 345 passed. Server pytest in 4
groups on 8a8177ba: 105 failing ids, none of them new against 94114a89; browser tests run on this
machine now (they errored at the earlier base run), so the 13 files holding failures were rerun on
94114a89 and 8a8177ba in the same environment: 105 = 105, 0 new (server
`docs/p047/full-pytest-compare-94114a89-vs-8a8177ba.txt`, `failing-files-rerun-...txt`).

`--only-new` and the project memory on `.po`: the CLI still sends the whole file (JSON/ARB only)
and builds no memory lookup for `.po`, so neither can lose or repeat a slot; the server's
whole-entry reuse rule is covered by its unit tests (de reused, pl reused only with slot 2).

Left as it is:
- A slot whose category the model's answer lacks (and the repair could not add) takes the
  `other` form; the run's ICU warnings still name the missing category.
- A source `.po` whose language has 3+ slots and no `_PO_SLOT_CATS` row is not folded (old
  behaviour); every 3+-slot language in `_PLURAL_RULES` has a row.
- `check` reads a single-number slot loosely only for the count; the other placeholders are
  compared as before.

## Round 2: critic 21.11 (NOT ACCEPTED) and what changed

Verdict: `ops-logs/critic-p047-1121/VERDICT.md` (two blockers, each reproduced). Every fix below
was first seen failing: CLI `docs/p047/r2/cli-b2-test-red-e721b68.txt` (py, 4 failed),
`npm-b2-test-red-e721b68.txt` (npm, 4 failed), `cli-onlynew-test-red.txt` (the new
`--only-new`/claim/memory tests on e721b68, 8 failed); server
`i18n_tool docs/p047/r2/server-round2-test-red-88ee3052.txt` (20 failed).

### B1: one-form languages got `{{count}}` under `_one`

`{"msg_one": "One message from {{name}}", "msg_other": "{{count}} messages from {{name}}"}` to
ja: the server wrote the `other` text under `msg_one`, and `check` (0.2.45, 0.2.46 and the
candidate alike) failed on `invented placeholder {{count}}`. A language with one form needs no
form added, so the set is no longer folded for it: the server translates its own view of the
file (`translator._one_form_set`, `_with_members`, `_view`), with the set's keys one by one —
the request 0.2.46 sent. Other languages of the same job still get the folded string. A JSON
answer that lacks a form the SOURCE has (`one` dropped) is no longer filled with `other` either:
those forms go one by one (below).

e2e (`docs/p047/harness/compat.py`, `r2/compat.txt`): ja/zh/ko, py and npm translate, then
`check` 0.2.47 py + npm, 0.2.46 and 0.2.45 on every file: all exit 0 (before: all exit 1); and
ja.json/zh.json/ko.json are byte-identical to 0.2.46 + production. Server tests: ja, zh, ko,
vi, th, id, ms; ja beside pl in one job; nested object.

### B2: a broken or foreign Plural-Forms switched the count check off

`formats.po_loose_slots` (py) / `poLooseSlots` (npm): the single-number slots are read loosely
only when the file's formula parses, every value for n = 0..1000 is below its `nplurals`, its
`nplurals` equals the language's, and it gives the same slot as the language's formula for every
n = 0..1000. The language is the file's `Language:` header, else the `--langs` code. The
formulas are the server's own table (`_PLURAL_RULES`, what `translate` writes), mirrored as
`formats.PLURAL_RULES` / npm `PLURAL_RULES`; `test_detector_parity.py` fails on any difference
from the server's, and `npm/test/po-slots.test.js` on any difference between the ports. No
new table. A language the table does not have (de, es…: the server writes n != 1 there, whose
only single-number slot is msgstr[0], loose since before 0.2.47) stays strict.

`r2/b2-vs-msgfmt.txt` (every case of `tests/test_po_single_number_slots.py`, py, npm, msgfmt -c
0.22.5): `plural=n;` in ru.po and Hebrew's formula with `nplurals=2` fail in all three (msgfmt:
"plural expression can produce values as large as …"); Hebrew's formula in ru.po fails in KAERIS
and passes msgfmt (it does not compare the formula with the language); the Arabic/Hebrew/Polish
loose cases pass in all three. Critic's own files: candidate e721b68 exit 0, 0.2.47 py and npm
exit 1, 0.2.46 exit 1.

### Old CLI on the new server: what production gives

The new forms (JSON/YAML/ARB sets, `.po` slots) go only to a client that says it takes them:
`/api/translate` form field `plurals=cldr` (`translator._fold_plurals(every_form=...)`,
`translate_file(plural_forms=...)`). The CLI's User-Agent carries its version (`kaeris-cli/0.2.46`),
but the server reads a field, not a version: what matters is that the client can merge
`cart.saved_few` beside its siblings and read an Arabic `msgstr[1]` without `%d`, and a field
says that for every client (py, npm, the MCP server through `KaerisClient`, a curl user)
without parsing versions. 0.2.47 sends it in every request (py `client._multipart`, npm
`api.submit`). Without it the server folds only what production folds (Android, Fluent).

Who else calls `/api/translate`:
- the site (studio and demo, `frontend/app.js`) and the public API (curl, docs/api.html): no
  field, so production behaviour. Safe: their ZIP is a whole file, but a user who then runs
  `kaeris check` 0.2.46 in CI would see an Arabic `.po` `msgstr[1]` without `%d` as a lost
  placeholder. Turning it on for the site is one line in `app.js` (`form.append("plurals",
  "cldr")`), best after 0.2.47 has been on PyPI/npm for a while. Not done in this package.
- the MCP server (`mcp/kaeris_mcp`) submits through `kaeris.client.KaerisClient` and merges with
  `kaeris.incremental.merge_translation`: with kaeris 0.2.47 installed it sends the field and
  merges the new forms in place; with an older kaeris it sends nothing and gets production
  behaviour. Consistent either way.

`/api/config` says `"plural_forms": "cldr"` (the capability, read by the CLI below).

e2e: CLI d5535f0 (0.2.46) on the new server vs on production, the critic's `--only-new` scenario
(new `cart.saved_*` set, edited `files.other`, `new_title`, three `--only-new` runs) and full
translates of i18next and `.po` to pl/ar/ja: every file byte-identical, no dotted key at the root.

### New CLI on the production server

Release order: **server first, then the CLI** (merge to main and PyPI/npm). The server change is
inert for every existing client (no field), so it can go out alone. A CLI released first works,
as described here, but writes no new forms until the server does.

0.2.47 on 94114a89: `/api/config` has no `plural_forms`, so `--only-new` does not send a set only
to complete its forms (`KaerisClient.adds_plural_forms`, asked once per run, false when it
cannot be asked); a set is still sent whole when one of its forms changed (production translates
its keys one by one, as before). Full translate: production ignores the field, 0.2.46 output.
e2e: the critic's scenario, runs 2 and 3 "up to date" with 0 model calls (before: the Polish set
sent and charged on every run); pl.json/de.json byte-identical to 0.2.46 on production; a pl
target with one/other only: "up to date" twice, 0 model calls. `check --langs pl` stays red on
the forms production never writes, as with 0.2.46.

CI parity: the server's CI clones the CLI branch of the same name, else main; the CLI's parity
tests need the new server (`_json_plural_sets`, `_PLURAL_RULES` gate). So: server branch and CLI
branch merge together, server deployed first, then the CLI published.

### Small things

- Broken model answer (stub modes plain / noother / short): a JSON set or `.po` entry whose
  folded answer is not one plural with `other` (or a JSON answer missing a source form) is
  translated form by form, as before 0.2.47 (`translator._broken_groups`, `_forms_one_by_one`,
  progress total grows by its batches). e2e: no English source left in pl/ar/ja for JSON and
  `.po` in all three modes; `check` names the forms the fallback could not add (pl/ar JSON red,
  as 0.2.46 on production), `short` as before (forms missing named).
- QA words: on a folded JSON/`.po` set the run's QA drops the fold's own `{count}` (and the
  variable the answer named its plural by) and says "the plural came back broken" / "plural is
  missing …", never "ICU" (`translator._plural_qa_words`). e2e: no `{count}`/ICU in any broken
  run's output.
- `--only-new` wording: "pl: 1 more key(s) of plural sets sent with them" only beside other
  keys; a set completed on its own says "pl: sending 2 key(s) of plural sets whole, so every
  form pl needs is written".
- Project memory count: lines of sets a `plural_forms` server translates again are not counted
  as remembered (and not sent as `reuse`; the server would not use them). e2e: second full run
  de,pl,ja with the memory: 0.2.47 says 10 (de 4, ja 4, pl 2), the candidate said 12.
- `--dry-run` with `--only-new` counts the plural sets the run would send whole.
- Version 0.2.47 (`pyproject.toml`, `kaeris/__init__.py`, `npm/package.json`; npm reads its
  version from package.json). Release notes: `docs/p047/RELEASE-NOTES-CLI-0.2.47.md`.

### Known, not in this package

- `msgstr[0]` is never held to the number, in any language (before 0.2.47 too): Russian `one`
  (1, 21, 31…) without `%d` passes `check`, msgfmt -c rejects it. Making it strict changes what
  passes today: a separate decision.
- A one-form language's `.po` keeps step 2 (its one slot is the `other` form); `msgstr[0]` is
  loose, so `check` is green there.
- `--no-only-new` writes no lock, so the next `--only-new` does not see an edit made in between
  (the critic's `files.other`); same on 0.2.46.
- The site/demo and API do not ask for the new forms yet (above).

### Result

Commits: see the branch log after e721b68 (CLI) and 88ee3052 (server). e2e: `r2/e2e-matrix-after.txt`
134/134 GREEN (the 134 earlier rows: every format, py + npm, `--only-new`, `.po` slots);
`r2/compat.txt` (the cases above).

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
