kaeris 0.2.47

## Translate writes every plural form the target language needs

0.2.46 wrote Polish `few`/`many` for an ICU plural, but an i18next `items_one`/`items_other`
pair or a nested `one`/`other` object came back with the source's two forms, and
`kaeris check` then failed on the file it had just written. Now:

- i18next `items_one`/`items_other`, nested JSON and Rails YAML `items.one`/`items.other` get
  the forms `kaeris check` asks for: Polish, Russian and Ukrainian `few` and `many`, Arabic
  and Welsh all six, Czech and Slovak `few`. A form check does not ask for (French `many`) is
  not written.
- `.po`: each `msgstr[i]` gets its own form, in the order the target's `Plural-Forms` numbers
  them. Polish `msgstr[2]` is the `many` form, not a copy of `msgstr[1]`; Arabic gets six.
- Japanese, Chinese, Korean, Vietnamese, Thai, Indonesian and Malay have one form, so nothing
  is added: each key is translated on its own, as in 0.2.46.
- If the model's answer is not a usable plural, the forms are translated one by one, as in
  0.2.46. The source text is not written in their place.
- i18next ordinals (`place_ordinal_*`) are translated key by key, as before.

The forms come from the KAERIS server. The CLI asks for them in every request; a server that
does not add them translates the file as it did for 0.2.46.

## `--only-new`

- A plural set that lacks a form the target language needs is work: the whole set is sent,
  and `kaeris check` is green afterwards. An edit to one form re-sends its set.
- A new form is written next to its siblings (`items_few` inside `cart`), not at the top
  of the file as a key named `"cart.items_few"`.
- Against a server that does not add forms, a set is not sent just to complete it, so a run
  costs nothing when nothing changed.
- "N of them come from the project memory" no longer counts plural sets the server translates
  again (a Polish set: the memory has only the source's forms).

## Check: `.po` slots that stand for one number

A `.po` slot may leave the number out when the file's `Plural-Forms` formula picks it for
exactly one value of n: Arabic `msgstr[1]` (one) and `msgstr[2]` (two), Hebrew `msgstr[1]`
(two). `msgstr[1] "ملف واحد"` passes; 0.2.46 called it a lost `%d`. This holds only when the
formula is sound (every slot it gives exists) and gives the same slot for every n as the
formula KAERIS writes for the file's `Language`. A formula like `plural=n;`, another language's
formula, or a language KAERIS has no formula for keeps the 0.2.46 reading.

| In a target `.po` | 0.2.46 | 0.2.47 |
|---|---|---|
| `ar` `msgstr[1]` / `msgstr[2]`, `he` `msgstr[1]` without `%d` | fails | passes |
| a slot that covers many numbers (Polish `msgstr[1]`, Arabic `msgstr[4]`) without `%d` | fails | fails |
| `nplurals=3; plural=n;`, or Hebrew's formula in a Russian file, a slot without `%d` | fails | fails |

Nothing that passed 0.2.46 fails 0.2.47.

`msgfmt -c` is looser: it lets a slot go without the number when the formula picks it for
fewer than five values of n in 0..1000 (Czech and Slovak `few`, Irish `msgstr[2]` and
`msgstr[3]`, Scottish Gaelic `msgstr[1]`), and it does not compare the formula with the
language. KAERIS asks for the number there.

## npm

`npx kaeris check` reads `.po` slots the same way. `npx kaeris translate` asks for the plural
forms too.
