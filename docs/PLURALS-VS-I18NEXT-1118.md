# Plurals: `kaeris check` vs `i18next-cli` (18.11.2026)

The question every i18n thread asks: *does it catch an incomplete plural?* A Polish plural with
only `one` and `other` shows "5 przedmiotu" for every number from 2 up; ICU, JSON and the compilers
all accept it.

## Setup

- **kaeris**: branch `p13-plurals-1118` of this repository, `python -m kaeris check --source … --langs <lang>`.
- **i18next-cli 1.91.0** (npm, installed into a temporary folder). `lint` checks *source code*
  (hard-coded strings, interpolation arguments against the translation); `status <lang>` compares
  each locale with the keys found in the code and expands plurals with `Intl.PluralRules`. Both
  were run, because `lint` alone has no plural check for locale files.
- **Corpus**: the 38 cases of `tests/test_plurals_by_cldr.py` (also replayed against the npm port
  in `npm/test/corpus/plurals-*`). For i18next-cli each i18next/ICU-JSON case became a project:
  `locales/{en,<lang>}/translation.json`, `src/app.js` with one `t()` per key (plural sets with
  `{ count }`, ordinals with `{ count, ordinal: true }`, ICU keys with exactly the arguments they
  use) and `i18next.config.js`. Android, ARB, xcstrings, .po, Fluent and Rails YAML are formats
  i18next-cli does not read: `n/a`.

## Summary

| | kaeris check | i18next-cli |
|---|---|---|
| i18next `_one/_other` in pl, ar | fault, exit 1 | `status`: absent `_few/_many…`, exit 1; `lint`: nothing |
| ja with `_other` only, pl ordinals with `_ordinal_other` only | pass | pass |
| ICU plural incomplete (flat, inside a select, inside a plural) | fault, exit 1 | no signal: the same answer for a broken and a correct file |
| ICU correct (pl/ru/ar/cy complete, en, ja) | pass | `status` exit 1 (expects `_one/_other` keys), `lint` exit 1 (`gender` "not used") — false alarms |
| Android `<plurals>`, ARB, xcstrings (substitution, device), .po, Fluent, Rails YAML | checked | not read |

What i18next-cli does well: for an i18next v4 project it derives the forms from `Intl.PluralRules`,
so it knows every language, not only the ones in our table (fr/es/it `many` included). Our table
is deliberately conservative (see "Limits").

## Case by case

| case | expected | kaeris check | i18next-cli lint | i18next-cli status |
|---|---|---|---|---|
| android ja: other only | pass | —, exit 0 | n/a (format) | n/a (format) |
| android pl: one/other | fail | items (plural): ICU plural is missing the few/many form(s) pl requires, exit 1 | n/a (format) | n/a (format) |
| android ru: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| arb ja: other only | pass | —, exit 0 | n/a (format) | n/a (format) |
| arb pl: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| arb pl: plural inside select one/other | fail | cartItems: ICU plural inside the select arm 'male' is missing the few/many form(s) pl requires, exit 1 | n/a (format) | n/a (format) |
| ftl ja: other only | pass | —, exit 0 | n/a (format) | n/a (format) |
| ftl pl: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| ftl pl: plural inside select one/other | fail | items$0.male$0 (plural): ICU plural is missing the few/many form(s) pl requires, exit 1 | n/a (format) | n/a (format) |
| i18next ar: _one/_other only | fail | plural form missing: cart.item_few — ar needs the zero/one/two/few/many/other forms of 'cart.item', exit 1 | no issues, exit 0 | absent: cart.item_few, cart.item_many, cart.item_two, cart.item_zero, exit 1 |
| i18next en: control | pass | —, exit 0 | no issues, exit 0 | 100%, exit 0 |
| i18next ja: _other only | pass | —, exit 0 | no issues, exit 0 | 100%, exit 0 |
| i18next pl: _one/_other only | fail | plural form missing: cart.item_few — pl needs the one/few/many/other forms of 'cart.item', exit 1 | no issues, exit 0 | absent: cart.item_few, cart.item_many, exit 1 |
| i18next pl: complete (ordinal other only) | pass | —, exit 0 | no issues, exit 0 | 100%, exit 0 |
| icu-json ar: complete | pass | —, exit 0 | Parameter "gender" is not used in translation string (error), exit 1 | absent: cart.items_few, … +8, exit 1 |
| icu-json ar: plural inside plural one/other | fail | cart.deep: ICU plural inside the plural arm 'zero' is missing the few/many/two/zero form(s) ar requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json cy: complete | pass | —, exit 0 | Parameter "gender" is not used (error), exit 1 | absent: cart.items_few, … +8, exit 1 |
| icu-json cy: flat plural one/other | fail | cart.flat: ICU plural is missing the few/many/two/zero form(s) cy requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json cy: plural inside select one/other | fail | cart.items: ICU plural inside the select arm 'male' is missing the few/many/two/zero form(s) cy requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json en: control | pass | —, exit 0 | Parameter "gender" is not used (error), exit 1 | absent: cart.items_one, cart.items_other, cart.flat_one, cart.flat_other, exit 1 |
| icu-json ja: other only, nested | pass | —, exit 0 | Parameter "gender" is not used (error), exit 1 | absent: cart.items_other, cart.flat_other, exit 1 |
| icu-json pl: complete | pass | —, exit 0 | Parameter "gender" is not used (error), exit 1 | absent: cart.items_few, … +4, exit 1 |
| icu-json pl: flat plural one/other | fail | cart.flat: ICU plural is missing the few/many form(s) pl requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json pl: plural inside plural one/other | fail | cart.deep: ICU plural inside the plural arm 'one' is missing the few/many form(s) pl requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json pl: plural inside select one/other | fail | cart.items: ICU plural inside the select arm 'male' is missing the few/many form(s) pl requires, exit 1 | same as the complete file, exit 1 | same as the complete file, exit 1 |
| icu-json ru: complete | pass | —, exit 0 | Parameter "gender" is not used (error), exit 1 | absent: cart.items_few, … +4, exit 1 |
| po ja: nplurals=1 | pass | —, exit 0 | n/a (format) | n/a (format) |
| po pl: header nplurals=2 | fail | Plural-Forms declares nplurals=2, but pl needs 3 plural forms — the extra forms can never be selected, exit 1 | n/a (format) | n/a (format) |
| po pl: nplurals=3, two msgstr | fail | %d file: the file declares 3 plural forms, this entry has no msgstr[2], exit 1 | n/a (format) | n/a (format) |
| po ru: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| xcstrings ja: other only | pass | —, exit 0 | n/a (format) | n/a (format) |
| xcstrings pl: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| xcstrings pl: substitution + device plural one/other | fail | cart (sub n, plural): ICU plural is missing the few/many form(s) pl requires, exit 1 | n/a (format) | n/a (format) |
| yaml ja: other only | pass | —, exit 0 | n/a (format) | n/a (format) |
| yaml pl: complete | pass | —, exit 0 | n/a (format) | n/a (format) |
| yaml pl: one/other | fail | plural form missing: cart.items.few — pl needs the one/few/many/other forms of 'cart.items', exit 1 | n/a (format) | n/a (format) |

kaeris: 38 of 38 as expected. i18next-cli: 5 of 5 i18next-suffix cases right (`status`); the 12
ICU cases get one answer whatever the file holds.

## Limits (kaeris)

- **Languages judged**: `_CLDR_REQUIRED` (ru uk pl cs sk hr sr lt ro ar lv sl he cy) for the extra
  forms, `_NO_SINGULAR` (ja zh ko vi th id ms km lo my yo ig jv su) for `other`-only. Romance
  `many` (fr/es/it/pt, CLDR 38+) is not demanded on purpose — CLDR-version-sensitive, a false
  alarm there teaches people to ignore the check. i18next-cli is wider here.
- **Ordinals** (`selectordinal`, i18next `_ordinal_*`): only `other` is required; there is no
  ordinal table.
- **.po**: the form count comes from the header (`nplurals`); Welsh has no entry in the nplurals
  table (gettext tradition disagrees: 4 or 6 forms).
- **.stringsdict** is not one of the 13 formats `kaeris check` reads (nor the server's).
- A nested plural that the translation *removes* (flattened to plain text in one arm) is not
  reported: only the top-level block count is compared.
