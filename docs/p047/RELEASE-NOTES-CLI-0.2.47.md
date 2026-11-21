kaeris 0.2.47

## Translate writes every plural form the target language needs

In 0.2.46 an ICU plural got the Polish `few`/`many` forms, but an i18next `items_one`/`items_other`
pair or a nested `one`/`other` object came back with only the source's two forms. For an i18next
pair `kaeris check` then failed on the file translate had just written; for nested JSON and YAML it
printed a warning. Now:

- i18next `items_one`/`items_other`, nested JSON and Rails YAML `items.one`/`items.other` get
  the forms `kaeris check` asks for: Polish, Russian and Ukrainian `few` and `many`, Arabic all
  six, Czech and Slovak `few`. A form check does not ask for (French `many`) is not written.
- `.po`: each `msgstr[i]` gets its own form, in the order the target's `Plural-Forms` numbers
  them. Polish `msgstr[2]` is the `many` form, not a copy of `msgstr[1]`; Arabic gets six.
- Japanese, Chinese, Korean, Vietnamese, Thai, Indonesian and Malay `.po`: `msgstr[0]`, the only
  slot, now holds the plural form ("%d files"). 0.2.46 put the singular there ("One file"),
  which these languages then showed for every number. This is a fix.
- JSON and YAML in Japanese, Chinese, Korean, Vietnamese, Thai, Indonesian and Malay: nothing is
  added, and each key is translated on its own, as in 0.2.46.
- i18next `_zero` and Rails `zero` mean "the count is 0" in every language, so they are
  translated as that, as in 0.2.46. "Your cart is empty" stays "Your cart is empty".
- A form is never filled with the text of another form. If the model's answer misses a form,
  or is not a usable plural at all, that plural is translated form by form, as in 0.2.46. If a
  form still has no text of its own after that (or, in `.po`, repeats `msgstr[1]`), the run's
  QA names it. The source text is never written
  in its place.
- i18next ordinals (`place_ordinal_*`) are translated key by key, as before.

The forms come from the KAERIS server. The CLI asks for them in every request; a server that
does not add them translates the file as it did for 0.2.46.

## What it costs

- The first `--only-new` run after the update sends every plural set that lacks a form its
  language needs, and those strings are charged. This hits Polish, Russian, Ukrainian, Czech,
  Slovak, Croatian, Serbian, Lithuanian, Romanian, Latvian, Slovenian, Hebrew and Arabic.
  German, French, Spanish and Japanese sets are not sent again.
- A full run (`--no-only-new`) pays for those sets every time. The project memory holds the
  source's forms, so a Polish set is never complete from memory.
- The GitHub Action installs `kaeris>=0.2.12`, so it picks up 0.2.47 on its next run with no
  change on your side. Its first run in these languages will cost more than usual.

## `--only-new`

- A plural set that lacks a form the target language needs is sent again, whole, and
  `kaeris check` is green afterwards. An edit to one form re-sends its set.
- A new form is written next to its siblings (`items_few` inside `cart`), not at the top
  of the file as a key named `"cart.items_few"`.
- Against a server that does not add forms, a set is not sent just to complete it, so a run
  costs nothing when nothing changed.
- "N of them come from the project memory" no longer counts plural sets the server translates
  again (a Polish set: the memory has only the source's forms).

## Check: `.po` slots that stand for one number

A `.po` slot may leave the number out when the file's `Plural-Forms` formula picks it for
exactly one value of n: Arabic `msgstr[1]` (one) and `msgstr[2]` (two), Hebrew `msgstr[1]`
(two). `msgstr[1] "ملف واحد"` passes; 0.2.46 called it a lost `%d`. This holds only when:

- the formula is sound (every slot it gives exists),
- it gives the same slot for every n as the formula KAERIS writes for the file's language,
- the file's `Language:` is the language you check it as (`--langs`),
- the formula is at most 1000 characters and plainly written.

Otherwise the 0.2.46 reading applies.

| In a target `.po` | 0.2.46 | 0.2.47 |
|---|---|---|
| `ar` `msgstr[1]` / `msgstr[2]`, `he` `msgstr[1]` without `%d` | fails | passes |
| a slot that covers many numbers (Polish `msgstr[1]`, Arabic `msgstr[4]`) without `%d` | fails | fails |
| `nplurals=3; plural=n;`, a slot without `%d` | fails | fails |
| `ru.po` with Hebrew's formula, or with `Language: he`, a slot without `%d` | fails | fails |

Nothing that passed 0.2.46 fails 0.2.47.

The reverse is not true. If translate 0.2.47 writes an Arabic `.po` and your CI still runs
`kaeris check` 0.2.46, that check fails on `msgstr[1]` without `%d`. Update the check too.

`msgfmt -c` is looser: it lets a slot go without the number when the formula picks it for
fewer than five values of n in 0..1000 (Czech and Slovak `few`, Irish `msgstr[2]` and
`msgstr[3]`, Scottish Gaelic `msgstr[1]`), and it does not compare the formula with the
language. KAERIS asks for the number there.

## npm

`npx kaeris check` reads `.po` slots the same way. `npx kaeris translate` asks for the plural
forms too.

## For kaeris-mcp

`kaeris.check.plural_set_faults` reads plural sets the way `kaeris check` does. kaeris-mcp uses
it so that `kaeris_status` does not call a Polish `items_few` an extra key.
