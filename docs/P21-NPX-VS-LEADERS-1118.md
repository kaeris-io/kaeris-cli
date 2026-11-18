# `npx kaeris translate`: plan, and the same task with Lingo.dev CLI

Goal: someone in an empty folder with one locale file runs `npx kaeris translate` and gets the
translated files next to it, with paths and placeholders intact, without Python.

## 1. The leader, run on 18.11.2026

Lingo.dev CLI 0.138.12 (`npx lingo.dev@latest`), Windows 11, Node 24.19, a temporary folder
outside the repository with one `i18n/en.json` of five strings:

```json
{
  "greeting": "Hello, {name}!",
  "items": "You have %s items in your cart",
  "buy_link": "See <a href=\"/how-to-buy/\">how to buy</a>",
  "docs": "Read the docs at https://example.com/docs/start",
  "save": "Save changes"
}
```

No account was created and no login was made.

| Step | What happened | Time |
|---|---|---|
| `npx -y lingo.dev@latest --help`, empty npm cache for it | installs its tree: 351 entries at the top of `node_modules` (one deprecation warning) | 29.9 s |
| `init -y -s en -t de -b json -p "i18n/[locale].json"` | asks "Use (and create) default path i18n/[locale].json?" despite `-y`; with no terminal the prompt dies with `ExitPromptError`, no `i18n.json` written | – |
| `run` without `init` | `i18n.json not found` | – |
| `i18n.json` written by hand, `run` | `you are not authenticated`: `lingo.dev login`, `--api-key` or `LINGO_API_KEY` | 4.9 s to the refusal |
| `run --pseudo` (local, no API) | `i18n/de.json` written | 8.1 s |

What `--pseudo` wrote (this is their local pseudo-localization, not the AI path, which needs an
account and was not run):

```json
{
  "greeting": "Ĥèļļø, {ñãmè}!⚡",
  "items": "Ýøû ĥãṽè %š íţèmš íñ ýøûŕ çãŕţ⚡",
  "buy_link": "Šèè <ã ĥŕèƒ=\"/ĥøŵ-ţø-ƀûý/\">ĥøŵ ţø ƀûý</ã>⚡",
  "docs": "Ŕèãð ţĥè ðøçš ãţ ĥţţþš://èxãmþļè.çøm/ðøçš/šţãŕţ⚡",
  "save": "Šãṽè çĥãñĝèš⚡"
}
```

Every placeholder, the tag, the path and the URL were changed in that mode. How their AI path
treats them is unknown from this run.

## 2. Us against Lingo.dev

Same machine, same day, same five-string file. Our numbers are from section 6.

| | Lingo.dev CLI 0.138.12 | `npx kaeris translate` (this branch) |
|---|---|---|
| Account needed to translate | yes (login, API key or env) | no: anonymous demo, 10,000 characters per file, 8 languages per run (server's `/api/key/info`, `/api/config`, 18.11) |
| Config file needed | yes, `i18n.json`; `init -y` still prompts and dies without a terminal | no: file and `--langs` on the command line; `kaeris.json` optional |
| What `npx` installs | 351 entries at the top of `node_modules` | 1 package, 0 dependencies, 30 files, 84 KB tgz / 276 KB unpacked |
| Empty folder to a translated file, cold `npx` | not reached: 29.9 s to install, then a refusal for want of an account | 7.4 s, install and translation together (run 1) |
| `{name}`, `%s`, `/how-to-buy/`, URL | all four changed by `--pseudo`; AI path not run | all four intact (run 1); `%@`, `%d`, `/how-to-buy/` intact in `.strings` (run 2) |

## 3. How the Python CLI translates (kaeris/cli.py, kaeris/client.py, 0.2.45 candidate)

- **Key or anonymous.** `--key`/`-k` (before or after the command) or `KAERIS_API_KEY`; sent as
  `X-API-Key`. Without one the run is the anonymous demo: one line
  `→ no key: free demo limits 10,000 chars per file, 8 languages per run, get a key: …`.
  `--openrouter-key` / `KAERIS_OPENROUTER_KEY` → `X-OpenRouter-Key` (Lifetime/BYOK).
  `--api-url` / `KAERIS_API_URL`: https only, http for loopback only; a redirect to another host
  or from https to http is refused (the key would follow it).
- **API calls of one file:**
  1. `GET /api/languages` – every code checked before anything is sent; unknown → exit 1.
  2. `GET /api/key/info`, `GET /api/config` – only for the no-key line.
  3. `POST /api/translate`, multipart: `file` (bytes, original name), `languages`, and only when
     set `glossary` (keep terms, comma-joined), `tone`, `icu=true`, `app_context` (≤300 chars),
     `translate_service_keys=true`, `model`, `models` (JSON), `terms` (JSON, from
     `kaeris-glossary.json`), `reuse`, `verify*`. Answer `{job_id, edit_token, warnings}`.
     429 → wait `Retry-After` (≤60 s) and send again, 3 times. Connection refused → retry; a
     connection dropped after sending → never sent twice.
  4. `GET /api/status/<job>` every second (slower after a 429) until `done` or `error`;
     progress lines `→  40%  de`. `error` with `retryable` → the job is sent again (2 times).
  5. `GET /api/download/<job>` – a ZIP of `<lang><ext>` members (`values-<lang>/strings.xml`
     for Android, the whole `.xcstrings` for a String Catalog). Member names are checked: no
     absolute path, drive, `..` or nesting deeper than one folder.
  6. `GET /api/preview/<job>` – QA: `_warnings` (lost placeholders, "may break your app" /
     "check the meaning"), `_qa` (overflow). Best effort.
  7. `GET /api/receipt/<job>` with `X-Job-Token: <edit_token>` – the two "Run: …" lines.
  8. `GET /api/key/info` – the monthly volume line, for a key that has one.
  Reads (2, 4–8) wait out a 429 up to 5 times.
- **Where files go** (`_target_path`): `en.json` → `de.json` beside it; `locales/en/x.json` →
  `locales/de/x.json`; `app_en.arb` → `app_de.arb`; `res/values/strings.xml` →
  `res/values-de/strings.xml`; `en.lproj/Localizable.strings` → `de.lproj/Localizable.strings`;
  otherwise `<dir>/<lang>/<name>` with a warning. `--out` replaces the base folder. A name that
  exists on disk in another case (`zh-hant.json`) is written under its own name. Written paths are
  printed on stdout, one per line; everything else goes to stderr.
- **`kaeris.lock`** is read and written only by `--only-new` (JSON/ARB): it records source
  hashes and the settings, so an edited source string or a changed tone re-translates.
- **`kaeris-tm.json`** (project memory) is read and written on every JSON/ARB run unless `--no-tm`.
- **`--keep` / `--glossary`**: terms kept verbatim, sent as `glossary`. **`--glossary-file`** (or
  `glossary_file` in kaeris.json, else `./kaeris-glossary.json`): `{"terms": [{"term",
  "translations": {lang: word|[words]}, "case_sensitive", "pos", "note"} | {"term", "keep": true}]}`;
  its `keep` terms join `--keep`, the rest go as `terms` with only this job's languages.
- **Exit codes:** 0 done; 3 some languages fell back to source text; 1 a file failed (server
  refusal, unreadable file, unknown language, no source); 2 bad usage or a refusal outside the
  file loop.

## 4. What the npm package does in its first version

Ported, with the Python flag names, defaults and messages:

- `kaeris translate [files…]` (paths and globs), `--langs/--to/-l`, `--out/-o`, `--source-lang`,
  `--keep/--glossary`, `--glossary-file`, `--context`, `--tone`, `--icu/--no-icu`,
  `--translate-service-keys`, `--model`, `--jobs/-j`, `--quiet/-q`, `--receipt PATH`,
  `--key/-k` before or after the command, `--openrouter-key`, `--api-url`, `--config`, and the
  same fields of `kaeris.json`.
- The API calls 1–8 above, on the built-in `fetch`; the same https/loopback rule, the same
  same-host redirect rule, the same ZIP member rule, retries on 429 and on a refused connection.
- The output layout of section 3, including `<lang>.lproj`, Android `values-<lang>` and a String
  Catalog written over its source.
- QA lines from the preview, the receipt lines, the monthly volume line, the no-key line.
- Exit codes 0 / 3 / 1 / 2 as above. A refusal from the server is one line naming the HTTP code
  and the server's sentence, plus what to do for 401 (check the key), 402 and plan limits (the
  pricing line), 429 (one run at a time) and 5xx (try again later).

Not in the first version (each prints what to use instead and exits 2, so nothing is charged by
surprise): `--only-new`, `--assume-current`, `--lock` (and `"only_new": true` in kaeris.json),
`--verify`, `--verify-all`, `--back-lang`, `--apply-fixes`, `--dry-run`, `--json`, `--tm`,
`--digits`, `--lang-case lower`. Also not here: the project memory (`kaeris-tm.json` is neither read
nor written, so a second whole-file run is charged again in full, as with `--no-tm`).

## 5. Tests

`npm/test/translate.test.js`, `node --test`, a fake HTTP server inside the test on 127.0.0.1:

- JSON source → `de.json`, `fr.json` beside it; the bytes the server sent are written.
- a non-JSON format: `en.lproj/Localizable.strings` → `de.lproj/Localizable.strings`.
- `locales/en/common.json` → `locales/de/common.json`; `--out`.
- the multipart request carries the file, `languages`, `glossary`, `tone`; `X-API-Key` only when a
  key is given; placeholders and paths in the downloaded file are not touched by the client.
- 401, 402, 429 (after the retries), 500, 503: one clear line, exit code not 0, no file written.
- an archive member `../evil.json` is refused and nothing is written.
- an unknown language is refused before any file is sent.
- `http://` to a host that is not loopback is refused.

## 6. Results

Tests: `npm test` 234 passed, 0 failed (210 before; 24 new in `npm/test/translate.test.js`, all
seen failing before the code existed).

Against https://kaeris.dev, no key, 18.11.2026. Each run: `npm pack`, then in a fresh folder outside
the repository `npx -y --package=<tgz> kaeris translate …`, timed from the start of `npx` to its
exit. Three translations in all.

| Run | Source | Command | Result | Time |
|---|---|---|---|---|
| 1 | `i18n/en.json`, 5 strings | `translate i18n/en.json --langs de` | `i18n/de.json`; `{name}`, `%s`, `href="/how-to-buy/"`, `https://example.com/docs/start` intact; exit 0; 144 characters charged | 7.4 s, cold `npx` |
| 2 | `App/en.lproj/Localizable.strings`, 5 strings | `translate App/en.lproj/Localizable.strings --langs de,fr --keep KAERIS -q` | `App/de.lproj/…`, `App/fr.lproj/…`; `%@`, `%d`, `/how-to-buy/`, `KAERIS` intact; exit 0 | 6.7 s, `npx` cached |
| 3 | `locales/en/common.json` (nested, ICU plural, `{{name}}`), `kaeris.json` with `source`, `langs: ["uk"]`, `icu: true` | `translate` (no arguments) | `locales/uk/common.json`; plural with Ukrainian `one/few/many/other`, `{{name}}`, `/how-to-buy/` intact; exit 0 | 8.7 s, cold `npx` (new tgz) |

Two refusals, which translate nothing: a wrong key gives
`✗ HTTP 401: Invalid API key. Get a valid key at kaeris.dev/developer` and one line on what to do,
exit 1; `--langs de,xx` gives `Unknown language code: xx` with the codes offered, exit 1, before
the file is sent.

Seen in run 1, on the server's side: the model ended three German strings with a full stop the
source does not have, one of them right after the URL (`…/docs/start.`).
