# Plurals, variant B (19.11): new findings warn, 0.2.43's still fail

Owner's choice P1.3, working decision B. Variant A (release-0.2.45 @ b5bf1af, release-0.2.46 @
8948de2): every plural-form finding of 0.2.45 is an error, exit 1. Variant B (release-0.2.45-
pluralwarn, and release-0.2.46-pluralwarn, which merges it like 0.2.46 merges 0.2.45): a plural
finding that the published 0.2.43 did NOT fail is a warning (exit 0 when nothing else fails;
`--strict` fails on it, exit 1 like every warning). Whatever 0.2.43 failed still fails. Message
text is the same in both variants.

## The baseline is the PUBLISHED 0.2.43

The package on PyPI is commit c9a026e (every file of `kaeris/` identical), not the tag v0.2.43
(572bf51). c9a026e already let a block that spells its cases out (`=N` arms and no category
besides `other`) owe no CLDR form: `{n, plural, =0 {…} other {…}}` passed in Polish. Round 1 read
the tag and missed it (critic, 19.11).

## Which findings are new in 0.2.45

| finding | 0.2.43 | B |
|---|---|---|
| top-level ICU plural, language of the 0.2.43 table (ru uk pl cs sk hr sr lt ro ar lv sl he), not `=N`+`other` only, lacking a form of that table | error | error |
| the same block when it is `=N` arms + `other` only: 0.45 owes it `one` unless it has `=1` | none | warning |
| top-level ICU plural, any other language (de fr es it pt nl ... cy): the `one` rule C7, Welsh | none | warning |
| ICU plural/select nested in another block's arm, forms or `other` | none | warning |
| top-level ICU block without `other`; dropped block; dropped `=N` | error | error |
| i18next `_one/_other` set, language of the 0.2.43 table | error | error |
| i18next set in Welsh; Rails / nested-object set (`items.one`, `items.other`) | none | warning |

The level is decided per block in `_icu_findings` (it returns what `_icu_faults` returns, each with
"error"/"warn"; `_icu_faults` is now `[msg for msg, _ in _icu_findings(...)]`). Not from the
message: Polish `=0 + other` and `few/many/other` both read "missing the one form(s) pl requires",
and only the second failed in 0.2.43. tests/test_plurals_variant_b.py holds the 0.2.43 loop
verbatim and checks, over 10 944 generated strings (arm sets × `=N` sets × offset × nesting × 19
languages), that B has an ICU error exactly where 0.2.43 had an ICU fault.

## Steps

1. `kaeris/detectors.py`: `_PLURAL_RED_SINCE_043`, `_icu_findings`; `string_faults` takes the
   level from it.
2. `kaeris/check.py`: `_plural_set_faults` returns (msg, severity); a warning goes to
   `result["warnings"]` with severity `warn`, so `ok` stays true and exit is 0 without --strict.
3. npm port: `PLURAL_RED_SINCE_043` in tables.js (gen_tables.py), `icuFindings` in detectors.js,
   the same split in check.js.
4. Tests first (red on the code before): tests/test_plurals_variant_b.py, npm pairs/baselines,
   test_detector_parity compares `_icu_findings` with the backend's.
5. Live matrix against PyPI 0.2.43: 0 exit-code changes green -> red, Python and npm.
6. README and npm README: the new plural findings are listed under the warnings.

## Server (i18n_tool), not changed here

Against release-1066 (94114a89); tried on a throwaway copy (patch and runs in i18n_tool
docs/p23/checks/variant-b/round2/):

- `backend/translator.py`: `_PLURAL_RED_SINCE_043` after `_NO_SINGULAR` (line 1136); the body of
  `_icu_faults` (line 1761) moves into `_icu_findings` with a level per finding, and
  `_icu_faults` returns its messages — the same as kaeris/detectors.py.
- `backend/checker.py` line 104-105: `for msg, level in T._icu_findings(src, tgt, lang):
  add("icu_broken", level, msg)`.
- `backend/tests/test_check_matches_cli.py`: a de value without `one` and a pl `=0 + other` in the
  corpus; today's corpus has neither, so it would not notice the page and the CLI disagreeing.
- test_detector_parity.py compares `_icu_findings`: once this reaches the kaeris-cli branch the
  i18n_tool CI clones (same name, else main), `detector-parity` is red until translator.py has it.
