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
   ~~`#` from the model becomes the set's own count placeholder (`{{count}}`,
   `%{count}`, `{count}`).~~ Not so until round 4 (critic round 3, B5): the placeholder every form
   shares was taken, `{{name}}` in "One message from {{name}}" / "{{count}} messages from
   {{name}}", and with two shared placeholders `#` stayed in the file. The rule now: see Round 4.
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
   one slot = `other`. `#` -> the entry's own count placeholder (`%d`, `%s`, `{n}`), as for JSON
   (round 4: which placeholder that is, and what happens when it cannot be told, see Round 4).
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
- ~~A slot whose category the model's answer lacks (and the repair could not add) takes the
  `other` form~~ — changed in round 3: the entry goes as before 0.2.47 and the run names it.
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
  behaviour. Not consistent as written in round 2: its `kaeris_status` ran the bare key diff and
  called the new `items_few`/`items_many` "extra/stale" (critic round 2). Fixed in round 3, below.

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

Commits: see the branch log after e721b68 (CLI) and 88ee3052 (server). e2e on CLI d9b0689 +
server 636c089a: `r2/e2e-matrix-after.txt` 134/134 GREEN (the 134 earlier rows: every format,
py + npm, `--only-new`, `.po` slots); `r2/compat.txt` 36/36 GREEN (the cases above; "info" rows
are recorded, not judged).

Full suites: CLI py 881 passed, 37 skipped (the one new skip: the server-table parity test, which
runs beside the backend: 4 passed there); npm 350/350. Server pytest, 4 groups
(`--splits 4 --group N`, Windows, same `.venv`), 94114a89 with `cli/` = d5535f0 vs 636c089a with
`cli/` = this branch: 777 failing ids each, 0 new, 0 gone (the failures and errors are this
machine's browser/env tests, the same on both; i18n_tool
`docs/p047/r2/full-pytest-compare-94114a89-vs-636c089a.txt`).

Server change after the e2e found nothing but a review did: a JSON source form the answer lacks
first always sent the set form by form, which would have dropped i18next `_zero` sets in Polish
to the fallback; now `other` stands in when it says the same placeholders
(`_missing_form_unsafe`, test `test_a_dropped_form_with_the_same_placeholders_takes_other`).
**This was blocker B3 of the round-2 critic; reverted and replaced in round 3.**

## Round 3: critic round 2 (NOT ACCEPTED, B3) and what changed

Verdict: `ops-logs/critic-p047-1121/round2/VERDICT.md`. B1 and B2 confirmed closed there.

### B3: a form the answer lacked took the `other` text

Round 2 (`636c089a`) filled a source form missing from the model's answer with the `other` text
when the placeholders matched. i18next `_zero` went to the model as the CLDR category `zero`;
de/pl/ru have none, so the model left it out: de `cart_zero` became the `cart_other` text, pl/ru
`left_zero` the `other` form where n=0 takes `many`. `check` stayed green.

Rule now (director's decision): **the text of one form never silently stands in for another.**
Server (`translator.py`):
- `_fold_label`: i18next / Rails `zero` (`_JSON_PLURAL_FORMATS`) travels as the ICU exact match
  `=0 {…}` — its meaning in i18next and Rails (count == 0, any language) — never `zero {…}`.
  The memory reuse (`_fold_reuse`) builds the same `=0`.
- `_json_forms` → (forms from the answer, `own`) or None: `_zero` is the `=0` arm; lost, it is
  `own` (that key translated on its own, as 0.2.46 sent it). A category the target has (de
  `one`, pl `few`, any `_CLDR_REQUIRED` form) missing → None: the set goes form by form (the
  round-1 fallback). A source category the target lacks (a ru source's `few` into de) missing →
  `own`. `_plural_redo` gives `_forms_one_by_one` per language {set: categories}; warnings of a
  set stay unless the whole set was redone; the "exact-match =0 dropped" warning goes when `=0`
  was translated on its own; a failed second try is named (`kept`).
- `.po`: a slot category the answer lacks → the entry goes as before 0.2.47 (msgid and
  msgid_plural one by one, msgstr[2..] repeat msgstr[1]) and `_plural_gaps` names it
  ("… without every form pl needs; msgstr[2..] (many) repeat msgstr[1], as before 0.2.47").
  Round 2 put the `other` text in slot 2 without a word. **Round 3 critic (B4): the server named
  it, but neither CLI printed `_qa[lang].plurals`; fixed in round 4.**
- Found on the way: an answer that spells the number `#` was measured before `#` became
  `{{count}}`, so QA said "{{count}}" was missing from forms that all have it (round 2 too).
  `_plural_qa_words(laid_out=…)` drops that.

Known limit: Latvian's CLDR `zero` covers 0, 10, 11–19, 20…; a source `_zero` ("cart is empty")
lands in lv `_zero` as in 0.2.46, and i18next shows it for 10 too. The source file's design;
same as 0.2.46. A source *in* Latvian with `_zero` would travel as `=0` too (not seen in use).

Tests, red first: server `tests/test_plurals_critic_round3.py` on c9118a03 12 failed / 2 passed
(i18n_tool `docs/p047/r3/b3-test-red-c9118a03.txt`), green 68/68 with round 2's and the fold
tests (`b3-test-green.txt`); the round-2 tests that pinned the old behaviour were rewritten
(`test_a_dropped_zero_is_translated_on_its_own`, `test_a_short_answer_goes_as_before_and_is_named`).
e2e (`harness/compat.py` case `b3`, stub modes normal and the new `drop-zero`): source
`cart_zero` (other words), `left_zero` (same words as `_other`), de/pl/ru. On server c9118a03
11 RED (`r3/compat-b3-red-on-c9118a03.txt`); on the branch every row green: `=0` sent, never
`zero {`; with `drop-zero` exactly the six `_zero` keys sent on their own; each `_zero` is its
own text; check py/npm exit 0 with every form; de.json byte-identical to 0.2.46 on production.

Harness fix: the CLI was meant to run from its tree via PYTHONPATH, but the "runs from" line was
printed from the session's working directory, where another kaeris tree won the import.
`harness/run_cli.py` now puts the tree first and drops imported kaeris modules on every call
(compat and matrix); each call prints the file that answered.

### Plural table parity in a CI that runs

`tests/data/server_plural_tables.json` is the server's `_PLURAL_RULES`, `_PLURAL_DEFAULT`,
`_CLDR_REQUIRED`, `_NO_SINGULAR`, `_HAS_ONE` (written by `tests/data/refresh_server_plural_tables.py
<backend>`). kaeris-cli CI, every push: `tests/test_plural_tables_snapshot.py` (py copies) and
`npm/test/plural-tables-snapshot.test.js` (npm copies) must equal it — no skip. Server side:
`test_detector_parity.py::test_plural_table_snapshot_is_the_servers` (server CI, release machine)
and the server's own `backend/tests/test_plural_tables_snapshot.py` with a pinned copy
`backend/tests/data/plural_tables.json`: it must be the server's tables (fails on any table edit
until refreshed) and equal the CLI's snapshot (`cli/` clone in the server CI, `KAERIS_CLI`
locally). Drift check (`r3/plural-snapshot-drift-check.txt`): one changed row in py, in npm or in
the server each fails exactly its check; restored, all green.
What still has no running CI: a server table change is caught by the server's own tests, which
run only when the server CI runs (billing) — hence the local run in the release checklist below.

### MCP: new forms are not "extra/stale"

`kaeris_status` and `kaeris_list_missing_keys` ran `chk.diff_locale` alone and listed Polish
`items_few`/`items_many` under "extra" (the tool says "extra/stale keys"; an agent may delete
them). Now `_diff_by_target_forms`: `diff_locale` then `chk.plural_set_faults` (new public name of
`_plural_set_faults`, CLI 0.2.47; falls back to the private one on 0.2.44–0.2.46, to the plain
diff before): owed forms are not extra, a ja file without `_one` is complete, and a set missing
its forms gets the CLI's fault (the status verdict now matches `kaeris check`). i18n_tool
`mcp/` and kaeris-mcp (branch `plural-translate-1121`, own worktree `p047-mcp-1121`; not
published, version unchanged) carry the same `server.py` (`test_public_repo_matches` green
against that clone). Test `mcp/tests/test_plural_forms_are_not_extra.py`: red on 94114a89
(4 failed), green with kaeris 0.2.47 and with 0.2.46.

### Small things

- `Language:` against `--langs`: a `.po` whose `Language` is not the language it is checked as
  (same base and same row of the table, so `pt_BR`/`pt` and `ar_EG`/`ar` agree, `he`/`ru` and
  `pt_PT`/`pt` do not) is read strictly.
- Plural-Forms limits, py and npm alike: over 1000 characters not evaluated (40k tokens took
  10 s); nesting over 50 (`(`, `!`, `-`, `?:`), a value beyond 2^53−1, `/` or `%` of a negative →
  strict. Shared corpus `npm/test/po-degenerate.json` (17 headers) read by both test suites;
  before: py and npm disagreed on 3 (200 parens, n^6, a 17-digit literal), now 17/17 each
  (`r3/po-degenerate-before-after.txt`).
- `docs/api.html` (the `plurals` field): the page exists in 10 languages (`frontend/<lang>/docs/
  api.html`), so it is not edited here. **Task for the site:** describe the optional
  `/api/translate` form field `plurals=cldr` (every CLDR form of the target for JSON/YAML/ARB
  sets and `.po` slots) in `frontend/docs/api.html` and its nine translations.

### Release checklist

1. Before anything goes out, on the release machine: the CLI branch nested as `cli/` in the
   server branch, `KAERIS_BACKEND=<server>/backend`, run `tests/test_detector_parity.py`,
   `tests/test_formats_match_the_server.py`, `tests/test_po_single_number_slots.py`,
   `tests/test_translate_completes_plural_sets.py`, `tests/test_plural_tables_snapshot.py`
   (0 skipped) and the server's `tests/test_plural_tables_snapshot.py` with `KAERIS_CLI` set.
   Required while the server CI does not run; record the output.
2. Server: merge `plural-translate-1121` (i18n_tool), deploy. Inert for every existing client.
   Check `/api/config` says `"plural_forms": "cldr"`.
3. CLI: merge `plural-translate-1121` (kaeris-cli) to main; CI green on the merge commit.
4. Publish PyPI 0.2.47, then npm 0.2.47. The GitHub Action picks it up by itself.
5. kaeris-mcp: merge its `plural-translate-1121`, bump the version and require `kaeris>=0.2.47`
   at its own release; keep i18n_tool `mcp/` identical (`test_public_repo_matches`).
6. Only then turn `plurals=cldr` on for the site (studio/demo, `frontend/app.js`) and describe it
   in `docs/api.html` (task above): a site user whose CI still runs `check` 0.2.46 would see an
   Arabic `.po` fail.

### Result (round 3)

On CLI dbc53cd + server 65e4b44c (backend as of ccf0a8a8), raw output in `docs/p047/r3/`:
- e2e `e2e-matrix.txt` 134/134 GREEN; `compat.txt` 54/54 GREEN (round 2's 36 + 18 B3 rows).
  The first final compat run was 53/54 (`compat-final-try1-stub-log-race.txt`): the stub's cargo
  log lost pl's line when two languages wrote at once; pl.json itself was right. The stub log now
  writes under a lock; rerun 54/54.
- CLI py `cli-py-full.txt` 904 passed, 38 skipped (all on the CI allow-list); npm
  `cli-npm-full.txt` 354/354; parity beside the server `cli-parity-with-server.txt` 78 passed,
  0 skipped. kaeris-cli CI success on dbc53cd.
- Server pytest, 4 groups (`--splits 4 --group N`, Windows, same `.venv`), 94114a89 with `cli/` =
  d5535f0 vs the branch with `cli/` = this branch: 777 failing ids each, 0 new, 0 gone
  (i18n_tool `docs/p047/r3/full-pytest-compare-94114a89-vs-branch.txt`).
- MCP: i18n_tool `mcp/tests` 96 passed (8 skipped: no MCP SDK here), kaeris-mcp clone 42 passed.

Not verified: a real model on `=0` (does it keep the arm; the repair asks for it again) — needs
a paid probe; the server CI (not running); MCP end to end with the real SDK.

## Round 4: critic round 3 (NOT ACCEPTED, B4 + B5) and what changed

Verdict: `ops-logs/critic-p047-1121/round3/VERDICT.md`. B3 confirmed closed there for
JSON/YAML/nested. Every fix below was first seen failing on the round-3 heads (cli e782690,
server 59be40da, kaeris-mcp 5d64b1d): CLI `docs/p047/r4/cli-py-r4-test-red-e782690.txt` (py, 11
failed), `cli-npm-r4-test-red-e782690.txt` (npm, 3 failed: the two B4 tests and the shared
Plural-Forms corpus); server i18n_tool `docs/p047/r4/server-r4-test-red-59be40da.txt` (19
failed, 3 passed) and `server-r4-one-slot-echo-red-f755ed69.txt` (2 failed, found by the rerun
below); MCP i18n_tool `docs/p047/r4/mcp-r4-test-red-5d64b1d.txt` (2 failed). Tests: server
`backend/tests/test_plurals_critic_round4.py`, CLI `tests/test_translate_says_plural_findings.py`
+ `npm/test/translate.test.js` (B4) + 10 cases in `npm/test/po-degenerate.json` (read by both
ports), MCP `tests/test_plural_forms_are_not_extra.py`.

### B4: the plural finding reaches the user

Was: the server put "the plural came back without every form pl needs; msgstr[2..] repeat
msgstr[1]" into `_qa[lang]["plurals"]`, but py `_show_qa` and npm `showQa` read only `overflow`
from `_qa`, so the run said "✓ Translation QA: no placeholder loss" over a Polish `.po` whose
msgstr[2] repeated msgstr[1] (critic `s9_b4.py`).

Now both ports print every `_qa[lang].plurals` line under "N plural(s) not written in every form
of their own:" and do not print the all-clear line beside it. The server's words say what was
written, per entry (`translator._po_old_way` reason + `_po_before_words` layout):

    [pl] '%d file': the answer had no many form; written as before 0.2.47: msgstr[0] (one) holds
         the singular, msgstr[2] (many) repeats msgstr[1] (few)

The same section carries a JSON set missing forms ("'cart': plural is missing the few/many
form(s) pl requires", `check` red on it too) and a form whose second try failed (below). Critic
`s9_b4.py` rerun (`r4/critic3/after-s9_b4.txt`): py and npm print the line, pl.po as before.

**Exit codes, decided:** a plural finding does not change the exit code of `translate` (0) or
`check` (0 for the repeated `.po` slot; 1 for missing JSON forms, as 0.2.46 on production).
Reasons: the entry is byte-for-byte what 0.2.46 wrote, and 0.2.46 users run `check` in CI on
such files today — a red Action over a file 0.2.46 accepted would be a regression of its own;
no QA finding of `translate` changes its exit code (a lost placeholder does not either: exit 3
is "a language fell back to source"); `check` reads the file and cannot see that slot 2 says the
`few` word (it would need a marker in the file). The run names it; the notes say it. The rule of
round 3 stays: one form's text never *silently* stands in for another.

### B5: `#` from the model is the count, or the set goes form by form

Was (`_count_token`, cc4b3c09): the placeholder every form shares, so "One message from
{{name}}" / "{{count}} messages from {{name}}" made `#` into `{{name}}` (de, pl, Rails
`%{name}`), and "{{count}} item in {{folder}}" (two shared) left `#` in the file; `check` red on
the file translate had just written (critic `s6_hash.py`, `s7_hash2.py`).

Now (`translator._count_token`): 1) JSON/YAML/ARB: the `other` form's placeholder named `count`
(i18next and Rails call the number that); `.po`: its one integer conversion (`%d`, `%1$d`,
`%lld`); 2) else the `other` form's only placeholder; 3) else the one `other` has and the
singular has not; 4) else none. With none and a `#` in the answer, the JSON set goes form by form
and the `.po` entry as before 0.2.47 (named) — never `#` or another placeholder in the file. A
form whose source has no number ("One message from {{name}}") answered with `#` would get a
placeholder its source lacks (`check`: invented): that form is translated on its own. Rerun
(`r4/critic3/after-s6_hash.txt`, `after-s7_hash2.txt`): de/pl JSON and Rails YAML have `{{count}}`
/ `%{count}`, `{{name}}` once, no `#`; `check` exit 0 on every file.

### Before release, items 1–5

1. **lv `.po`, a singular without the number** (critic: lv `msgstr[1]`, one: 1, 21, 31…, got "One
   message", `check` red where 0.2.46 was green). A slot past msgstr[0] that the Plural-Forms
   formula picks for more than one n (`_po_single_slots`, the server's own formulas through
   `gettext.c2py`) never gets a form without the count; such an answer sends the entry as before
   0.2.47 and the run says why ("msgstr[1] (one: 1, 21, 31…) stands for more than one number and
   needs %d, which the answer's one form leaves out; written as before 0.2.47: msgstr[0] (zero)
   holds the singular, msgstr[2] (other) repeats msgstr[1] (one)"). Arabic msgstr[1] (n = 1 only)
   keeps the singular without the number. Critic `s2_po_mem.py` rerun
   (`r4/critic3/after-s2.txt`): `check` py and npm exit 0 on all 96 .po checks (8 languages × 6
   stub modes × 2 ports); before: lv exit 1 in mode normal. A model that writes the number in
   the `one` form (`# ziņa`) gets the slots laid out (test).
2. **A failed second try dropped the language.** `_forms_one_by_one` ran the small redo part
   through `_translate_lang`, whose quality guard marked the whole language failed when its two
   echoed `_zero` keys came back untranslated: "Wrote 0 file(s)", exit 3, "260 charged" (critic
   `s8_fallback.py`). Now the part's verdict never touches `job.failed_langs` (nor clears a main
   pass that had failed, test); the part's failure is named ("'cart': the zero form(s) could not be
   translated on their own; the source text may stand there") and the file is delivered:
   `r4/critic3/after-s8_fallback.txt` exit 0, "Wrote 2 file(s)", de.json byte-identical to 0.2.46
   on production, `cart_zero` named twice ("may be untranslated" and the plural line). The refund
   in `main.py` for languages not delivered is not needed for this case any more (the languages
   are delivered and charged as 0.2.46 charges them, 260 = 260); it is unchanged, and its unit
   tests `TestPartialFailureRefund` (2) pass on the branch — the same file's `TestReuseIsNotBilled`
   fails with HTTP 500 on this machine on 94114a89 and the branch alike; the refund was not run end
   to end.
3. **Notes and doc** — corrected, see the notes: "The source text is never written in its place"
   (false when the second try fails: then the source text stays, as 0.2.46, and the run says so);
   "the run's QA names it" (true now, B4); "`#` becomes the set's own count placeholder" (true now
   with the B5 rule, and form by form when it cannot be told). Struck through above where this
   doc said them.
4. **kaeris-mcp floor**: `kaeris>=0.2.47` in `pyproject.toml` and the Dockerfile (kaeris-mcp and
   i18n_tool `mcp/`, identical) and in the bundle installer (`mcp/bundle/server/main.py`). Why
   0.2.47 and not 0.2.45: 0.2.45 is the first with the plural-set reading (`_plural_set_faults`,
   private), so `kaeris_status` would be right from there, but only 0.2.47 has the public
   `plural_set_faults` and the client that asks for every form and merges it beside its siblings —
   the files `kaeris_status` then reads. kaeris-mcp is released after kaeris 0.2.47 is on PyPI
   (release checklist step 5), so the floor is installable when it ships. Test
   `TheFloorIsAKaerisThatReadsPluralForms` holds every install line to it.
   `test_public_repo_matches` green against the kaeris-mcp worktree (`KAERIS_MCP_PUBLIC_CLONE`).
5. **False "missing %d" and slot names**: the run's QA on a folded entry is measured on the answer
   before `#` became `%d`; `_plural_qa_words` now drops "missing <count>" when every form that
   needs the number has it (`_laid_out`: a `.po` slot needs it where `check` does — past
   msgstr[0], not a single-number slot; a singular "One message" needs none), and a `.po`
   warning is filed under the msgid, never `<msgid_plural>\x01<i>` ("One message2"). Rerun
   `after-s6_hash.txt` / `after-s2.txt` mode hash: no "missing %d", no slot key.

Found by the reruns, fixed the same way (test first):
- **An answer that is the source fold itself** (the model left the plural out, stub `missfold`):
  de and lv got the English forms laid out as the answer ("may be untranslated"), and lv was told
  it lacked `zero` though `_zero` was there. Now an echo goes form by form, as 0.2.46 sent it
  (`_echoed`); "plural is missing the zero form(s)" is dropped when the set has the key.
- **ja/zh `.po` echo**: the echo lost its dead `one` arm on the way (`_drop_dead_plural_arms`) and
  was laid out as English "%d messages"; now it is recognised, goes form by form, and the one slot
  holds msgid_plural's translation (`after-s2.txt` mode missfold: `%d スオテテアキオテ`).

### Small things

- **py ≠ npm on exotic Plural-Forms**: both ports read the formula, `nplurals` and `Language:`
  with ASCII spaces and digits only (Python `\s`/`\d` are Unicode, JavaScript's `\s` another set).
  A BOM, NBSP, NEL, 0x1c/0x1f, an ideographic space or Arabic-Indic digits → strict (gettext reads
  spaces and tabs only). Critic `pf_cmp.py` rerun (`r4/critic3/after-pf_cmp.txt`): 40/40 py == npm
  (before 35/40).
- **`_PO_SLOT_CATS` in the snapshot**: `PO_SLOT_CATS` is in `tests/data/server_plural_tables.json`
  and the server's `backend/tests/data/plural_tables.json` (same file, `cmp` equal). Drift check
  (`r4/po-slot-cats-drift-check.txt`): ro reordered to one/other/few → the server's
  `test_the_pinned_tables_are_this_servers` and the CLI's `test_plural_table_snapshot_is_the_servers`
  both FAILED; restored, both pass.
- **"lv missing zero" on an empty answer**: gone with the echo rule (`after-s1.txt` mode missfold:
  no `[lv]` line).
- **`kaeris_list_missing_keys` lost plural faults**: it returns `plural_faults` (severity + the
  CLI's message) and `plural_fault_count`; the errors equal `kaeris check`'s faults (test).
- Not done: the server's half of the snapshot guard still runs only where the server's tests run
  (its CI is off for billing) — the release checklist runs it by hand. `--no-tm` in npm: not this
  package.

### Result (round 4)

On CLI 6862c55 (+ docs) and server 920eb308 (+ docs), raw output in `docs/p047/r4/`:
- critic's harness (`runner3.py`, stub, $0), `r4/critic3/after-*.txt`: s9 (B4) and s6/s7 (B5)
  green as above; s8 delivered; s2 96/96 `check` exit 0; s1 (JSON/YAML × 6 languages × 7 modes)
  `_zero` never another form's text (`after-s1-an1.txt`: 84 zero-own, 12 = the mode where the
  model never translates zero: source text, named), `check` red only where forms are missing
  (drop:few, missfold for pl/ru/ar/he — as 0.2.46 on production); s4 `_qa` printed by the CLI;
  s5 16/16 files IDENTICAL to 0.2.46 + production in both cross pairs, `.po` 60 = 60 charged.
- e2e `e2e-matrix.txt` 134/134 GREEN; `compat.txt` 54/54 GREEN (cand = the round-3 heads e782690
  and 59be40da).
- CLI py `cli-py-full.txt` 919 passed, 38 skipped; npm `cli-npm-full.txt` 356/356; parity beside
  the server `cli-parity-with-server.txt` 89 passed, 0 skipped.
- Server: plural tests (round 2/3/4, `.po`/JSON forms, snapshot with `KAERIS_CLI`) 214 passed
  (i18n_tool `docs/p047/r4/server-plural-tests-green.txt`, before the ja echo test); full pytest 4
  groups, 94114a89 (`KAERIS_CLI` = d5535f0) vs the branch: 942 vs 943 failing ids, the one new was
  this round's two raw files written with CRLF (made LF, test green): 0 new
  (`docs/p047/r4/full-pytest-compare-94114a89-vs-branch.txt`; both sides fail more than in round 3,
  777, the same ids on both — this machine's browser/env tests).
- MCP: i18n_tool `mcp/tests` 98 passed, 8 skipped (no MCP SDK); kaeris-mcp 44 passed, 4 skipped.

Not verified: a real model (how often it writes `#`, keeps `=0`, drops a form) — needs a paid
probe; the refund path for a language that really fails (unchanged, only its unit tests ran);
MCP end to end with the real SDK; the server CI (off).

## Round 5: critic round 4 (NOT ACCEPTED, B6 + B7) and what changed

Verdict: `ops-logs/critic-p047-1121/round4/VERDICT.md`. Four rounds in a row found a new blocker,
each in a new path where the server rewrites the model's answer. The rule of this round:
**new behaviour only where it is plainly right; where in doubt, byte for byte what 0.2.46 + the
production server (94114a89) gives — same file, same money, same exit code. An old client (no
`plurals=cldr`) gets production's answer byte for byte.** And a gate that holds every later
change to it: `harness/diff_gate.py` (below).

Every fix was first seen failing on the round-4 heads (cli fee2152, server 4ed9257c): server
`backend/tests/test_plurals_critic_round5.py` 26 failed / 7 passed when written
(i18n_tool `docs/p047/r5/server-r5-test-red-4ed9257c.txt`), the final file 27 failed / 8 passed
there (`server-r5-test-red-4ed9257c-final-tests.txt`: the 8 are guards that must hold on both);
CLI `tests/test_only_new_charges_once.py` 8 failed / 1 passed (`r5/cli-b7-test-red-fee2152.txt`,
same with the final file: `cli-b7-test-red-fee2152-final-tests.txt`).

### B6: a Django / brace `.po` passes check 0.2.46 and 0.2.47

Was: "One file" / "%(count)s files" (python-format; also `%(count)d`, python-brace `{count}`):
ja/zh/ko/vi/th/id/ms got "%(count)s ファイル" in their one slot, Arabic a form with the number in
msgstr[0] (zero) and one without it in msgstr[1]. `check` compares msgstr[0] with the msgid and the
rest with msgid_plural, and leaves the number out only where it is a lone printf integer
(`lone_count_to_hash`); so both 0.2.46 and 0.2.47 called the file translate had just written
broken. The same held, found on the way, for c-format "One message from %s" / "%d messages from
%s" (two printf conversions: `%d` is not lone).

Choice: the server, not check (the critic's option b). Teaching check 0.2.47 to read `%(count)s`
softly (option a) leaves every Action that pins `kaeris check` 0.2.46 red on a file it accepted
before. Rule (`translator._po_slot_check_fault`, called from `_po_old_way`): an entry is laid out
slot by slot only when every slot passes the placeholder comparison check makes for it —
msgstr[0] against msgid, the rest against msgid_plural, a lone printf integer optional in
msgstr[0] and in a slot one number picks (`_po_single_slots`). Otherwise the entry goes as before
0.2.47 and the run says which slot and why ("msgstr[0] (zero) would not pass `kaeris check`
(invented placeholder %(count)s (not in source)); written as before 0.2.47: …"). A one-slot
language keeps the singular, as 0.2.46 ("…; msgstr[0] holds the singular, as before 0.2.47").
Since 0.2.47's softer reading covers only the lone printf integer, a slot that passes here passes
check 0.2.46 too — except a single-number slot without `%d` (Arabic msgstr[1]/[2], Hebrew
msgstr[1]), which the notes tell (diff_gate tag `po-single-slot-046`). Polish/Russian/Hebrew
Django entries keep their own forms (test).

### B7: `--only-new` pays for completing a set once

Was: a set the server cannot complete (unbalanced brace, ICU select inside, the model losing
`many`, `#` where `{{count, number}}` cannot be named) was sent whole and charged on every run.

Now (py; npm has no `--only-new`):
- `check.plural_set_foldable`: a set is sent to be completed only when the server folds it —
  every form plain text, balanced braces, no ICU block, no `#` of its own. Held to the server's
  own `_fold_plurals` by `test_detector_parity.py::test_the_sets_only_new_completes_are_the_sets_the_server_folds`
  (11 cases, beside the backend);
- a set sent whole that still lacks a form after the merge is written into `kaeris.lock`
  (`plural_incomplete`: {lang: {set: sha256 of its source forms}}) and not sent to be completed
  again until its source changes; translate says so once ("the server did not add every form pl
  needs to 1 plural set(s) (c); not sent again until its source changes — `kaeris check` names
  the forms"). An older client ignores the field (and drops it on rewrite; so does the kaeris-mcp
  incremental writer): the next 0.2.47 run then tries those sets once more;
- a set beside an edited form goes whole only where that buys a form (the server adds forms,
  the language needs one the set's source lacks): German or Japanese send the edited key alone,
  as 0.2.46; so does any language on a server without `plural_forms` (before: the whole set,
  more money than 0.2.46 on production).
Critic `s16`/`s17` rerun (`r5/critic4/after-s16.txt`, `after-s17.txt`): runs 2 and 3 "up to
date", 0 calls, as 0.2.46; notes ("What it costs") say it.

### Before release, items 1–3

1. **Old client, new server.** `_echoed` (the echo of the source fold) is only for the new folds
   (JSON/YAML/ARB sets, `.po`): Android and Fluent keep production's rule for every client; ja
   Android writes `other` only again. diff_gate: every old-client comparison identical (below).
2. **A `#` of the source's own** ("{{count}} posts in #general"): the set (or `.po` entry) is not
   folded — key by key, as 0.2.46, no new forms (`_fold_plurals`, `_fold_po_groups`). The CLI
   does not send such a set to be completed (`plural_set_foldable`).
3. **A language the second try translated is delivered.** The main pass no longer judges the new
   folds (`_translate_lang(quality_skip=...)`): an answer that leaves one out goes form by form
   anyway. After that second try fails, the language is judged on every source key as it now
   stands — the verdict 0.2.46 gave the same keys sent one by one: a file of plurals left in
   English is failed (not delivered, not charged, exit 3), two `_zero` keys among many are not
   (round 3's s8 stays delivered). Critic `s18` missfold: exit 0, ja/zh/ko/ar/pl delivered, check 0.

### Small things of round 4

- A right answer equal to its source ("{{count}} km" in German): no "source text was kept" when
  the set came back from its form-by-form try (`_plural_gaps(redone=...)`). The two extra calls
  stay: an identical answer cannot be told from an echo.
- `.po` `{count}` with a `#` answer: no false "placeholder {count} appears 2× in source" (QA words
  drop the count's arity measured on the fold).
- `%(num)d` in both forms with a `#` answer: not changed — the entry goes as before 0.2.47 and is
  named (no new behaviour where it is not needed).
- A second try that fails with HTTP 500: delivered and charged when the rest of the language is
  translated (the forms keep the source text, named), failed and not charged when the language
  reads as untranslated — in the notes now.
- kaeris-mcp version and its `.mcpb` bundle: bumped and rebuilt at its own release (checklist
  step 5), not in this package.

### The gate: `harness/diff_gate.py`

One script, three servers and three stubs started and stopped by PID, $0. Cells: 9 formats
(i18next, nested JSON, Rails YAML, `.po` printf / python-format / brace, Android XML, Fluent, ICU
in JSON; their sources hold `{{count}}`, `{{ count }}`, `{{count, number}}`, `%d`, `%1$d`,
`%(count)s`/`%(count)d`/`%(num)d`, `{count}`, `%{count}`, `{ $count }`, a literal `#`, a second
shared placeholder, a singular without the number, `_zero`, an ordinal set) × 9 languages (de pl
ru ar lv he ja zh ko; cy is refused by the server and compared on its own) × 12 stub modes
(normal, dropzero, drop:zero/one/two/few/many, hashall, missfold, echo:file, empty, fail500repeat
= a request the stub has already answered in this cell fails with HTTP 500, i.e. every retry of the
same request). Servers get the same env each: a keyless allowance large enough for the gate, and
the provider breaker off (3 failures in a row close the process to every job for 60 s, which would
carry one cell's 500s into the next cells). Each cell: new→new, 046→prod,
046→new; the language's file byte for byte, `kaeris check --json` of 0.2.46 and of this tree, and
per run the exit code and the receipt's metered characters. `--only-new` on JSON: twice from an
empty target (the second run must charge 0 and change nothing), and the upgrade (this CLI twice
on the target and lock 0.2.46 wrote: the first may complete sets, the second must charge 0).
046→new must equal 046→prod in everything. new→new may differ from 046→prod only as one of the
`INTENDED` entries, each with its guard (only plural keys/entries differ, header and other
entries identical, no key lost, check 0.2.46 and 0.2.47 report nothing the 0.2.46 file did not).

Result (`r5/diff-gate.txt`, cli 438d9cf + this harness, server 341cab93 vs 94114a89, 5005 s):

    # intended by tag: {"cldr-forms": 252, "onlynew-complete": 22, "po-slots": 199, "po-slots+po-single-slot-046": 5}
    # old client -> new server: 1449 comparisons, 0 differences
    TOTAL 2916 cells + 486 runs, 478 intended, 0 unintended (5005s)

Every `--only-new` second run (fresh and upgrade) charged 0 and changed nothing; cy was refused
alike by all three. `po-single-slot-046` = Arabic c-format "One message" msgstr[1] without `%d`
(check 0.2.46 only), the case the notes name.

The first full run (`r5/diff-gate-run1-fail500after1.txt`) had a stricter 500 mode,
`fail500after1` (every request of a language after its first fails) and the breaker on: 0
unintended in the other 11 modes; in that mode the new path's second try (an entry going as
before 0.2.47, e.g. Arabic "One message from %s") failed where 0.2.46 needed no second request,
the entry kept the source text (named), and the extra 500s tripped the provider breaker, so the
cells after it got HTTP 503. That is the known cost of the form-by-form fallback (notes: "When a
plural has to be translated form by form and that second try fails…"), not hidden. Eight rows
there were the harness's own sanity flag on 0.2.46 writing nothing with exit 0 (`--only-new`, ICU
JSON, model leaving every plural out / empty replies — the same in all three pairings); the flag
now fires only on a refused request.

### Result (round 5)

On cli 438d9cf (+ these docs and harness) and server 341cab93 (+ docs), raw in `docs/p047/r5/`:
- diff gate: above, 0 unintended, old client 0 differences.
- critic round 4 harness (`runner4.py`, $0) on the round-5 heads, `r5/critic4/after-s10..s18.txt`
  (before: `before-*.txt` on fee2152 + 4ed9257c): s12 Django — every language check 0.2.46 and
  0.2.47 exit 0 but Arabic c-format "One page" for check 0.2.46 (named in the notes); s16/s17 —
  runs 2 and 3 "up to date", 0 calls; s18 — missfold delivered, exit 0, ja/zh/ko/ar/pl check 0;
  s15 — 56/56 identical (was 54/56); s11 — de check 0 with "#general", no `#` left; s13 — no
  "source text was kept" for "{{count}} km".
- critic round 3 harness (`runner3.py`), `r5/critic3/after-s1..s9.txt`: s1 84 zero-own (12 = the
  mode where the model never translates zero: source text, named); s2 96/96 check exit 0; s5 16/16
  identical; s6/s7 8/8 check exit 0; s8 "Wrote 2", 260 = 260 charged; s9 the B4 line printed.
- e2e `r5/e2e-matrix.txt` 134/134 GREEN; `r5/compat.txt` 54/54 GREEN (cand = new = these heads).
- CLI py `r5/cli-py-full.txt`, npm `r5/cli-npm-full.txt`, parity beside the server
  `r5/cli-parity-with-server.txt` (0 skipped).
- Server (i18n_tool `docs/p047/r5/`): plural tests `server-plural-tests-green.txt` 134 passed, 3
  xfailed; MCP `mcp-tests-green.txt` 98 passed / 8 skipped (no SDK) and kaeris-mcp 44 passed / 4
  skipped; full pytest 4 groups `full-pytest-compare-94114a89-vs-branch.txt`: 942 vs 941 failing
  ids, NEW 0, GONE 1 (the base worktree has no `cli/` beside its backend).
- The ~165 ids (exactly 188 new, 23 gone between round 3 and round 4): i18n_tool
  `docs/p047/r5/ids-new-since-r3.txt`, each with its status base/branch in the split run, the 31
  files run alone (`rerun-*-files165.txt`) and the same with a made-up provider key; 148 say
  "OPENROUTER_API_KEY not configured" (the shell of round 4 and 5 has no provider key; round 3's
  raw output has none of these), 28 pass when their file runs alone, 2 are uvicorn log lines, 10
  other (tier limits answered 500, fixture teardown); with the made-up key 186/188 pass on both
  sides. Same status on base and branch in all three runs: 187/188, the one differing fails on
  the base only (no `cli/` there).

Not verified: a real model (how often it writes `#`, keeps `=0`, drops a form) — needs a paid
probe; the refund path end to end; MCP with the real SDK; the server CI (off for billing); npm
`--only-new` (not in the npm package).

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
