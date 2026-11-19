# Plurals, variant B (19.11): new findings warn, 0.2.43's still fail

Owner's choice P1.3. Variant A (release-0.2.46 @ 8948de2): every plural-form finding of 0.2.45 is
an error, exit 1. Variant B (this branch): a plural-form finding that 0.2.43 did NOT report is a
warning (exit 0 when nothing else fails; `--strict` fails on it, exit 1 like every warning).
Whatever 0.2.43 reported as an error stays an error. Message text is unchanged in both variants.

## Which findings are new in 0.2.45

Read off `git diff v0.2.43 8948de2 -- kaeris/detectors.py kaeris/check.py`:

| finding | 0.2.43 | B |
|---|---|---|
| top-level ICU plural, language in the 0.2.43 table (ru uk pl cs sk hr sr lt ro ar lv sl he) | error | error |
| top-level ICU plural, any other language (de fr es it en pt nl tr cy ...): the `one` rule C7, Welsh | none | warning |
| ICU plural/select nested in another block's arm ("ICU plural inside the select arm ..."), forms or `other` | none | warning |
| top-level ICU block without `other` | error | error |
| i18next `_one/_other` set, language in the 0.2.43 table | error | error |
| i18next set in Welsh (cy entered the table in 0.2.45) | none | warning |
| Rails / nested-object set (`items.one`, `items.other`) | none | warning |

Top-level ICU in a 0.2.43 language: every entry of that table holds `one`, so any form 0.2.45
finds missing (the `one` rule included) means 0.2.43 already failed the same block. The split is
therefore a function of the message and the language alone, and `_icu_faults` (compared with the
server by test_detector_parity) is not touched.

## Steps

1. `kaeris/detectors.py`: `_PLURAL_RED_SINCE_043` (the 13 languages above) and
   `_icu_fault_severity(msg, lang)`; `string_faults` tags each `_icu_faults` message with it.
2. `kaeris/check.py`: `_plural_set_faults` returns (msg, severity); a warning goes to
   `result["warnings"]` with severity `warn`, so `ok` stays true and exit is 0 without --strict.
3. npm port: `PLURAL_RED_SINCE_043` in tables.js (gen_tables.py), `icuFaultSeverity` in
   detectors.js, the same split in check.js.
4. Tests first (red on 8948de2): tests/test_plurals_variant_b.py (Python, live CLI exit codes),
   npm cases through pairs/baselines (gen_baselines.py), parity case for the new helper.
5. Regenerate npm baselines/tables; full pytest and `node --test`.
6. Live table: 0.2.43 / A / B / B --strict, Python and npm, same samples.

## Server (i18n_tool), not changed here

- `backend/translator.py`: the same `_PLURAL_RED_SINCE_043` and `_icu_fault_severity`.
- `backend/checker.py` `string_faults`: `add("icu_broken", T._icu_fault_severity(msg, lang), msg)`
  instead of ERROR, or /api/check fails what `kaeris check` passes.
- test_detector_parity.py on this branch compares `_icu_fault_severity` with the backend's:
  without step 1 on the server the `detector-parity` job of a same-named i18n_tool branch is red.
