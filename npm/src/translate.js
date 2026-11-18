// `kaeris translate` of kaeris/cli.py (cmd_translate, _start_one, _finish_one, _run_job,
// _write_members, _show_qa, _show_receipt, _show_quota) for whole files: the same flags, the same
// kaeris.json fields, the same output paths, lines and exit codes (0 done, 3 a language fell back
// to the source, 1 a file failed, 2 bad usage). What the npm package does not do yet is refused
// by name before anything is sent: see UNSUPPORTED.
import fs from "node:fs";
import { Client, DEFAULT_API, KaerisError, KaerisInterrupted, tmpSuffix } from "./api.js";
import { limitLine, retag } from "./cta.js";
import * as gl from "./glossary.js";
import { layoutState, outPath, splitLangs, canonLang } from "./layout.js";
import { findLang } from "./formats.js";
import * as pp from "./pypath.js";
import { color, err, info, ok, out, warn } from "./say.js";

export const KEY_DOCS_URL = "https://kaeris.dev/docs/key";
const APP_CONTEXT_LIMIT = 300;
const DEFAULT_JOBS = 4;
const RESTART_RETRIES = 2;
const RESTART_PAUSE = 20;
const TONES = ["neutral", "formal", "casual"];
const PYTHON = "pipx install kaeris";

// Flags of the Python package that this one does not have yet. Each is read (so it is not taken
// for a file name) and refused before anything is sent: a run that silently ignored --only-new
// would charge for the whole file.
const UNSUPPORTED = [
  { long: "--only-new", flag: true },
  { long: "--no-only-new", flag: true, dest: "only_new", const: false, supported: true },
  { long: "--assume-current", flag: true },
  { long: "--lock", value: true },
  { long: "--verify", flag: true },
  { long: "--verify-all", flag: true },
  { long: "--back-lang", value: true },
  { long: "--apply-fixes", flag: true },
  { long: "--dry-run", flag: true },
  { long: "--json", flag: true },
  { long: "--tm", value: true },
  { long: "--no-tm", flag: true },
  { long: "--digits", value: true },
  { long: "--lang-case", value: true },
];

export const TRANSLATE_OPTIONS = [
  { long: "--langs", short: "-l", aliases: ["--to"], value: true },
  { long: "--out", short: "-o", value: true },
  { long: "--source-lang", value: true },
  { long: "--keep", aliases: ["--glossary"], value: true, dest: "keep" },
  { long: "--glossary-file", value: true },
  { long: "--context", value: true },
  { long: "--model", value: true },
  { long: "--tone", value: true },
  { long: "--icu", flag: true },
  { long: "--no-icu", flag: true, dest: "icu", const: false },
  { long: "--translate-service-keys", flag: true },
  { long: "--jobs", short: "-j", value: true },
  { long: "--quiet", short: "-q", flag: true },
  { long: "--receipt", value: true },
  { long: "--key", short: "-k", value: true },
  { long: "--help", short: "-h", flag: true },
  ...UNSUPPORTED.map((o) => (o.supported ? o : { ...o, unsupported: true })),
];

const USAGE =
  "usage: kaeris translate [-h] [--langs LANGS] [--out OUT] [--source-lang SOURCE_LANG]\n" +
  "                        [--keep KEEP] [--glossary-file PATH] [--context CONTEXT] [--model ID]\n" +
  "                        [--tone {neutral,formal,casual}] [--icu] [--no-icu]\n" +
  "                        [--translate-service-keys] [--jobs N] [--quiet] [--receipt PATH]\n" +
  "                        [--key KEY]\n" +
  "                        [files ...]";

export const TRANSLATE_HELP = `${USAGE}

Translate a strings file through the KAERIS API and write each language next to it. Reads
./kaeris.json (or --config PATH) for defaults when files/--langs/etc. are omitted; precedence is
CLI flag > kaeris.json > built-in default. Without a key it runs as the free anonymous demo with
smaller limits (get a key: ${KEY_DOCS_URL}).

positional arguments:
  files                 Source file(s) (.json/.yml/.strings/.xcstrings/.md/.mdx/.po/.arb/.xml/
                        .csv/.xliff/.properties/.resx/.ftl); several paths and/or glob patterns
                        (e.g. 'locales/en/*.json'); optional if 'source' is set in kaeris.json

options:
  -h, --help            show this help message and exit
  --langs, --to, -l LANGS
                        Comma-separated target languages, e.g. es,fr,de; optional if 'langs' is
                        set in kaeris.json
  --out, -o OUT         Output directory (default: alongside each source, or 'out' in kaeris.json)
  --source-lang SOURCE_LANG
                        Base language code used to detect locales/<lang>/<namespace> layouts
                        (default: 'source_lang' in kaeris.json, else 'en')
  --keep, --glossary KEEP
                        Comma-separated terms to never translate, e.g. --keep 'KAERIS,GitHub'
                        (default: 'keep' in kaeris.json)
  --glossary-file PATH  Terms and how each language must say them (default: 'glossary_file' in
                        kaeris.json, else ./${gl.FILENAME} if it exists)
  --context CONTEXT     One line about what the app is, e.g. --context 'a bank app for
                        teenagers' (max ${APP_CONTEXT_LIMIT} chars; default: 'context' in kaeris.json)
  --model ID            Lifetime (BYOK): the OpenRouter model to translate with (default: 'model'
                        in kaeris.json; 'models' sets one per language). Other plans refuse it
  --tone {neutral,formal,casual}
                        Tone of voice (default: 'tone' in kaeris.json, else neutral)
  --icu                 Hint that values may use ICU MessageFormat (plurals/select)
  --no-icu              Disable the ICU hint (overrides kaeris.json's icu)
  --translate-service-keys
                        Also translate keys that start with '_' (copied untouched by default)
  --jobs, -j N          How many jobs to keep running on the server at once (default ${DEFAULT_JOBS})
  --quiet, -q           Suppress progress output
  --receipt PATH        Write a JSON record of the run (model, languages, characters charged and
                        reused, settings); counts only, no strings
  --key, -k KEY         API key, here or before the command (or env KAERIS_API_KEY)

Not in the npm package yet (use the Python package, ${PYTHON}): --only-new, --assume-current,
--lock, --verify, --verify-all, --back-lang, --apply-fixes, --dry-run, --json, --tm, --no-tm,
--digits, --lang-case. The project memory (kaeris-tm.json) is neither read nor written here.
`;

// ── small helpers ─────────────────────────────────────────────────────────────

const isMap = (v) => v instanceof Map;
const toPlain = (v) => (isMap(v) ? Object.fromEntries([...v].map(([k, x]) => [k, toPlain(x)])) : Array.isArray(v) ? v.map(toPlain) : v);
const cps = (s) => [...String(s)];
const fmtInt = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
const sleepFor = (s) => new Promise((r) => setTimeout(r, s * 1000));

function relpath(p) {
  try {
    return pp.relpath(p);
  } catch {
    return p;
  }
}

function writeAtomic(dest, data) {
  const tmp = `${dest}.${tmpSuffix()}.tmp`;
  fs.writeFileSync(tmp, data);
  try {
    fs.renameSync(tmp, dest);
  } catch (e) {
    try {
      fs.unlinkSync(tmp);
    } catch {
      /* already gone */
    }
    throw e;
  }
}

// 1_234_567 -> '1.2M', 45_000 -> '45k'. Always floors.
function fmtChars(n) {
  n = Math.max(0, Math.trunc(Number(n) || 0));
  if (n >= 1_000_000) return `${Math.floor(n / 100_000) / 10}M`;
  if (n >= 1_000) return `${Math.floor(n / 1_000)}k`;
  return String(n);
}

// A source spec (one path/glob or a list) -> the existing files, sorted, each once.
function resolveSources(raw) {
  const entries = Array.isArray(raw) ? raw : [raw];
  const found = new Set();
  for (let e of entries) {
    e = String(e).trim();
    if (!e) continue;
    if (/[*?[]/.test(e)) for (const m of pp.glob(e)) found.add(m);
    else found.add(e);
  }
  return [...found].filter((p) => pp.isfile(p)).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

// ── refusals ──────────────────────────────────────────────────────────────────

// A server refusal: the server's sentence, then what to do about it.
function refused(e) {
  const message = retag(e.message);
  err(message);
  const status = e.code;
  const line = limitLine(message, { status });
  if (line) out(line);
  if (status === 401 || status === 403) {
    info(`Check the key (--key or KAERIS_API_KEY), or run without one for the free demo. Keys: ${KEY_DOCS_URL}`);
  } else if (typeof status === "number" && status >= 500) {
    info("The server could not do this right now; nothing was written. Try again in a few minutes.");
  }
}

// ── after a job ───────────────────────────────────────────────────────────────

// kaeris/detectors.py warning_group: "meaning" (the app works, the words may be wrong) or "break".
const MEANING_WARNING_RE = /^(?:number |currency |may be untranslated|brand term |glossary[ :]|invented link|not a translation|source string reads like|truncated|translation adds a text-direction)|translated on its own|every string replaced by/i;
const warningGroup = (message) => (MEANING_WARNING_RE.test(message || "") ? "meaning" : "break");

async function showQa(client, job) {
  let data;
  try {
    data = await client.preview(job);
  } catch {
    return null;
  }
  const warnings = data._warnings || {};
  const qa = data._qa || {};
  let ph = 0;
  for (const [group, heading] of [["break", "may break your app"], ["meaning", "check the meaning before you ship"]]) {
    const lines = [];
    for (const [lang, kv] of Object.entries(warnings)) {
      for (const [k, found] of Object.entries(kv || {})) {
        const mine = (found || []).filter((f) => warningGroup(f) === group);
        if (mine.length) lines.push([lang, k, mine]);
      }
    }
    if (!lines.length) continue;
    ph += lines.length;
    warn(`${lines.length} translation(s) ${heading}:`);
    const limit = group === "break" ? 20 : 5;
    const shown = new Map();
    for (const [lang, k, found] of lines) {
      shown.set(lang, (shown.get(lang) || 0) + 1);
      if (shown.get(lang) > limit) continue;
      const said = found.map((f) => (/^[{%<$]/.test(f) ? `missing ${f}` : f));
      out(`    [${lang}] ${k}: ${said.join("; ")}`);
    }
    for (const [lang, n] of shown) if (n > limit) out(`    … and ${n - limit} more for [${lang}] — run with --verify (Python package) to list them all`);
  }
  let over = 0;
  for (const v of Object.values(qa)) over += (v.overflow || []).length;
  if (over) {
    warn(`${over} translation(s) may overflow your UI (grew much longer than source):`);
    let shown = 0;
    for (const [lang, v] of Object.entries(qa)) {
      for (const o of v.overflow || []) {
        if (shown >= 6) break;
        const grew = o.short ? `+${o.chars} chars` : `+${o.pct}%`;
        out(`    [${lang}] ${o.key}: ${grew}  "${cps(o.tr || "").slice(0, 50).join("")}"`);
        shown++;
      }
    }
  }
  if (!ph && !over) ok("Translation QA: no placeholder loss, no overflow risks");
  return data;
}

const PLAN_NAMES = { premium: "Pro", teamapi: "Team/API", byok: "Lifetime", team: "Scale", free: "Free key", anonymous: "Free" };

function fallbackLine(rec) {
  const fb = rec.fallback || {};
  if (!fb.model) return null;
  const where = (fb.languages || []).join(", ") || "?";
  const n = fb.batches || 1;
  return `backup model ${fb.model} answered instead of ${rec.model || "?"} (${n} batch${n !== 1 ? "es" : ""}, ${where}): ${fb.reason || "reason not given"}`;
}

function fmtReceipt(rec) {
  const langs = rec.languages || {};
  const chars = rec.characters || {};
  const settings = rec.settings || {};
  const mine = "characters" in rec;
  const delivered = langs.delivered || [];
  const failed = langs.failed || [];
  const backup = (rec.fallback || {}).model;
  const served = (rec.models_served || []).filter(Boolean).map((m) => (backup && m === backup ? `${m} (backup)` : m));
  const plan = rec.plan in PLAN_NAMES ? PLAN_NAMES[rec.plan] : rec.plan;
  const lines = [
    `Run: ${served.length ? served.join(" + ") : rec.model || "?"} · ${plan || "plan hidden"} · ${delivered.length}/${(langs.requested || []).length} languages · ${rec.strings || 0} strings · ${rec.seconds || 0}s`,
  ];
  if (!mine) {
    lines.push("     spend and settings are the job owner's — not shown here");
    return [lines, failed];
  }
  const bits = [`${fmtChars(chars.metered || 0)} charged`];
  if (chars.reused_not_charged) bits.push(`${fmtChars(chars.reused_not_charged)} reused free`);
  if (chars.refunded) bits.push(`${fmtChars(chars.refunded)} refunded`);
  const on = ["icu", "verify"].filter((k) => settings[k]);
  if (settings.tone && settings.tone !== "neutral") on.push(settings.tone);
  if (settings.context) on.push("context");
  lines.push("     " + bits.join(" · ") + (on.length ? "  ·  " + on.join(", ") : ""));
  return [lines, failed];
}

async function showReceipt(client, job, seen) {
  let rec;
  try {
    rec = await client.receipt(job);
  } catch {
    return null;
  }
  const [lines, failed] = fmtReceipt(rec);
  info(lines[0]);
  out(lines[1]);
  const backup = fallbackLine(rec);
  if (backup) warn(backup);
  for (const g of rec.glossary || []) (g.found_in_source ? seen.found : seen.absent).add(g.term);
  if (failed.length) warn(`not delivered: ${failed.join(", ")}`);
  return rec;
}

const QUOTA_WARN_PCT = 80;
const QUOTA_CRIT_PCT = 95;

function quotaLine(data) {
  const cap = data.month_cap || 0;
  if (!cap) return null;
  const used = Math.trunc(data.month_used || 0);
  const left = Math.trunc(data.month_remaining ?? Math.max(0, cap - used));
  const pct = (used * 100) / cap;
  const level = pct >= QUOTA_CRIT_PCT ? "crit" : pct >= QUOTA_WARN_PCT ? "warn" : "ok";
  const text = `Monthly volume: ${fmtChars(used)} of ${fmtChars(cap)} used · ${fmtChars(left)} left · resets ${data.month_resets || ""}`.replace(/[ ·]+$/, "");
  return [text, level];
}

async function showQuota(client) {
  let line;
  try {
    line = quotaLine(await client.keyInfo());
  } catch {
    return;
  }
  if (!line) return;
  const [text, level] = line;
  if (level === "crit") warn(text + "  — nearly out; raise it at kaeris.dev/pricing.html");
  else if (level === "warn") warn(text);
  else info(text);
}

// The text a glossary term can occur in: the values of a JSON/ARB file, else the file.
function sourceText(path) {
  let text;
  try {
    text = fs.readFileSync(path, "utf8");
  } catch {
    return "";
  }
  if (/\.(json|arb)$/i.test(path)) {
    try {
      const vals = [];
      const walk = (v) => {
        if (v && typeof v === "object") Object.values(v).forEach(walk);
        else vals.push(String(v));
      };
      walk(JSON.parse(text.replace(/^﻿/, "")));
      return vals.join("\n");
    } catch {
      /* not JSON after all */
    }
  }
  return text;
}

function sayAbsentGlossary(seen, files) {
  const sources = files.map(sourceText);
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const inText = (t, text) => new RegExp(`(?<![A-Za-z0-9_])${esc(t)}(?![A-Za-z0-9_])`, "i").test(text);
  const absent = [...seen.absent].filter((t) => !seen.found.has(t) && !sources.some((s) => inText(t, s))).sort();
  if (absent.length) warn(`${absent.length} glossary term(s) never appear in your source, so nothing kept them: ${absent.slice(0, 5).join(", ")}`);
}

// ── one file ──────────────────────────────────────────────────────────────────

function progressPrinter(label) {
  let last = -1;
  return (status) => {
    const total = status.total || 0;
    const done = status.progress || 0;
    if (total && done !== last) {
      const pct = Math.trunc((done / total) * 100);
      const lang = status.current_lang || "";
      const where = label ? `${label}  ${lang}` : lang;
      out(`${color("→", "36")} ${String(pct).padStart(3)}%  ${where}`);
      last = done;
    }
  };
}

function modelOpts(s, langs) {
  if (langs.length === 1) {
    const m = (s.models.size && findLang(s.models, langs[0])) || s.model;
    return m ? { model: m } : {};
  }
  const per = {};
  for (const l of langs) {
    const m = s.models.size ? findLang(s.models, l) : null;
    if (m) per[l] = m;
  }
  const opts = s.model ? { model: s.model } : {};
  if (Object.keys(per).length) opts.models = per;
  return opts;
}

async function runJob(client, fname, content, langs, s, label) {
  let job;
  let status;
  for (let attempt = 0; ; attempt++) {
    job = await client.submit(fname, content, langs, {
      glossary: s.keep, tone: s.tone === "neutral" ? "" : s.tone, icu: s.icu, appContext: s.context,
      translateServiceKeys: s.translateServiceKeys, ...modelOpts(s, langs), terms: gl.termsFor(s.glossary, langs),
    });
    if (attempt === 0) for (const w of client.jobWarnings.get(job) || []) warn(`${label || fname}: server: ${w}`);
    try {
      status = await client.poll(job, s.quiet ? null : progressPrinter(label));
      break;
    } catch (e) {
      if (!(e instanceof KaerisInterrupted) || attempt === RESTART_RETRIES) throw e;
      const pause = RESTART_PAUSE * (attempt + 1);
      warn(`${label || fname}: the server restarted mid-run (nothing was charged) — sending it again in ${pause}s (${attempt + 1}/${RESTART_RETRIES})`);
      await sleepFor(pause);
    }
  }
  return [job, status, await client.download(job)];
}

// Each downloaded member (`<lang><ext>`, `values-<lang>/strings.xml`, the whole `.xcstrings`)
// to the path the layout gives it.
function writeMembers(members, srcPath, outDir, sourceLang) {
  const written = [];
  for (const [name, data] of members) {
    let dest;
    if (name.toLowerCase().endsWith(".xcstrings")) {
      // A String Catalog holds every language: the result is an update of the source catalog.
      dest = outDir ? pp.join(outDir, pp.basename(srcPath)) : srcPath;
    } else {
      const parts = name.split("/");
      const folder = parts.length > 1 ? parts[parts.length - 2] : "";
      const lang = folder.startsWith("values-") ? folder.slice("values-".length) : pp.splitext(parts[parts.length - 1])[0];
      dest = outPath(srcPath, lang, outDir, sourceLang);
    }
    fs.mkdirSync(pp.dirname(dest) || outDir || ".", { recursive: true });
    writeAtomic(dest, data);
    written.push(dest);
  }
  return written;
}

async function finishOne(client, path, ticket, s, seen) {
  const [job, status, members] = await ticket;
  const written = writeMembers(members, path, s.out, s.sourceLang);
  const dirs = new Set(written.map((w) => pp.dirname(pp.abspath(w))));
  ok(`Wrote ${written.length} file(s)` + (dirs.size === 1 ? ` to ${[...dirs][0]}` : ":"));
  for (const w of written) process.stdout.write(w + "\n");
  await showQa(client, job);
  const rec = await showReceipt(client, job, seen);
  if (rec && s.receipt) {
    writeAtomic(s.receipt, JSON.stringify(rec, null, 2));
    ok(`Run receipt written to ${s.receipt}`);
  }
  const failed = status.failed_langs || [];
  if (failed.length) {
    warn(`${failed.length} language(s) fell back to source text (not translated): ${failed.join(", ")}`);
    return 3;
  }
  return 0;
}

// At most `n` jobs on the server at once; the rest wait their turn.
function limiter(n) {
  let active = 0;
  const queue = [];
  const next = () => {
    if (active >= n || !queue.length) return;
    active++;
    const [fn, resolve, reject] = queue.shift();
    fn().then(resolve, reject).finally(() => {
      active--;
      next();
    });
  };
  return (fn) => new Promise((resolve, reject) => {
    queue.push([fn, resolve, reject]);
    next();
  });
}

// ── the command ───────────────────────────────────────────────────────────────

async function unknownLangs(client, langs) {
  let known;
  try {
    known = await client.languages();
  } catch {
    return [];
  }
  if (!known || typeof known !== "object" || !Object.keys(known).length) return [];
  const offered = new Set(Object.keys(known).map(canonLang));
  const result = [];
  for (const l of langs) {
    if (offered.has(l)) continue;
    const near = [...offered].filter((c) => c.split("-")[0] === l.split("-")[0].toLowerCase()).sort();
    result.push(near.length ? `${l} (offered: ${near.join(", ")})` : l);
  }
  return result;
}

async function demoNotice(client) {
  let limits = "";
  try {
    const chars = (await client.keyInfo()).char_limit;
    const langs = (await client.config()).max_langs_anon;
    if (chars && langs) limits = `${fmtInt(chars)} chars per file, ${langs} languages per run`;
  } catch {
    /* the line still says what mode this is */
  }
  info(`no key: free demo limits${limits ? " " + limits : ""}, get a key: ${KEY_DOCS_URL}`);
}

const notYet = (what) => `${what} is not in the npm package yet: run without it, or use the Python package (${PYTHON}), which has it`;

export async function cmdTranslate(args, globals, loadConfig) {
  if (args._unsupported && args._unsupported.length) {
    err(notYet(args._unsupported[0]));
    return 2;
  }
  const [config, configPath] = loadConfig(globals.config);
  if (configPath) info(`Using config: ${configPath}`);
  const cfg = (k) => (config.has(k) ? toPlain(config.get(k)) : undefined);

  // kaeris.json settings this package cannot honour: refused, never silently dropped.
  if (args.only_new === undefined && cfg("only_new") === true) {
    err(`"only_new": true in ${configPath} is not in the npm package yet: pass --no-only-new to translate whole files, or use the Python package (${PYTHON})`);
    return 2;
  }
  for (const [key, plain] of [["lang_case", "keep"], ["digits", "native"]]) {
    const v = cfg(key);
    if (v !== undefined && v !== plain && v !== null && v !== "") {
      err(`"${key}": ${JSON.stringify(v)} in ${configPath} is not in the npm package yet: remove it, or use the Python package (${PYTHON})`);
      return 2;
    }
  }

  const raw = args.files && args.files.length ? args.files : cfg("source");
  if (!raw || (Array.isArray(raw) && !raw.length)) {
    err("No source file given (positional argument(s), or 'source' in kaeris.json)");
    return 1;
  }
  const files = resolveSources(raw);
  if (!files.length) {
    err(`No source file(s) found: ${Array.isArray(raw) ? raw.join(", ") : raw}`);
    return 1;
  }

  const langs = splitLangs(args.langs ? args.langs : cfg("langs"));
  if (!langs.length) {
    err("No target languages given (use --langs es,fr,de, or set 'langs' in kaeris.json)");
    return 1;
  }

  const s = {};
  const cfgKeep = cfg("keep") || cfg("glossary") || [];
  const keepRaw = args.keep ? args.keep : Array.isArray(cfgKeep) ? cfgKeep.join(",") : String(cfgKeep);
  s.keep = keepRaw.split(",").map((t) => t.trim()).filter(Boolean);
  try {
    s.glossary = gl.find(args.glossary_file, typeof cfg("glossary_file") === "string" ? cfg("glossary_file") : null);
  } catch (e) {
    if (e instanceof gl.GlossaryError) {
      err(e.message);
      return 2;
    }
    throw e;
  }
  if (s.glossary) {
    for (const t of s.glossary.keep) if (!s.keep.includes(t)) s.keep.push(t);
    info(`Glossary: ${s.glossary.entries.length} term(s), ${s.glossary.keep.length} kept as is`);
  }
  s.context = cps(String(args.context || cfg("context") || "").trim()).slice(0, APP_CONTEXT_LIMIT).join("");

  const cfgModel = cfg("model") ?? "";
  const cfgModels = config.has("models") ? config.get("models") : new Map();
  if (typeof cfgModel !== "string") {
    err('"model" in kaeris.json must be an OpenRouter model id, e.g. "openai/gpt-4.1"');
    return 2;
  }
  if (!isMap(cfgModels) || ![...cfgModels.values()].every((v) => typeof v === "string")) {
    err('"models" in kaeris.json must be an object of language -> model id, e.g. {"de": "openai/gpt-4.1"}');
    return 2;
  }
  s.model = String(args.model || cfgModel).trim();
  s.models = new Map([...cfgModels].map(([k, v]) => [k.trim(), v.trim()]).filter(([k, v]) => k && v));

  if (args.tone !== undefined && !TONES.includes(args.tone)) {
    err(`argument --tone: invalid choice: '${args.tone}' (choose from ${TONES.map((t) => `'${t}'`).join(", ")})`);
    return 2;
  }
  s.tone = args.tone ?? (TONES.includes(cfg("tone")) ? cfg("tone") : "neutral");
  s.icu = args.icu !== undefined ? args.icu : Boolean(cfg("icu"));
  s.translateServiceKeys = Boolean(args.translate_service_keys);
  s.out = args.out || (typeof cfg("out") === "string" ? cfg("out") : null) || null;
  s.sourceLang = args.source_lang || cfg("source_lang") || "en";
  const jobs = Number.parseInt(args.jobs ?? cfg("jobs") ?? DEFAULT_JOBS, 10);
  if (args.jobs !== undefined && !Number.isFinite(jobs)) {
    err(`argument --jobs/-j: invalid int value: '${args.jobs}'`);
    return 2;
  }
  s.jobs = Math.max(1, Number.isFinite(jobs) ? jobs : DEFAULT_JOBS);
  s.quiet = Boolean(args.quiet);
  s.receipt = args.receipt || null;

  if (s.out) fs.mkdirSync(s.out, { recursive: true });

  const client = new Client({
    apiUrl: globals.api_url || process.env.KAERIS_API_URL || DEFAULT_API,
    apiKey: args.key || globals.key || process.env.KAERIS_API_KEY,
    openrouterKey: globals.openrouter_key || process.env.KAERIS_OPENROUTER_KEY,
  });
  const unknown = await unknownLangs(client, langs);
  if (unknown.length) {
    err(`Unknown language code: ${unknown.join(", ")}. Run 'kaeris languages' for the list (codes like de, ja, pt-PT, zh-Hant).`);
    return 1;
  }
  if (!client.apiKey) await demoNotice(client);
  layoutState.warned = false;

  const multi = files.length > 1;
  const seen = { found: new Set(), absent: new Set() };
  const limit = limiter(s.jobs);
  // Jobs go to the server side by side (up to --jobs at once); results are written and reported
  // file by file, in order.
  const tickets = files.map((path) => {
    let content;
    try {
      content = fs.readFileSync(path);
    } catch (e) {
      return Promise.reject(new KaerisError(`Cannot read ${path}: ${e.message}`));
    }
    const fname = pp.basename(path);
    info(`Translating ${fname} → ${langs.join(", ")}`);
    const t = limit(() => runJob(client, fname, content, langs, s, multi ? fname : ""));
    t.catch(() => {}); // reported in its turn below
    return t;
  });
  let exitCode = 0;
  for (let i = 0; i < files.length; i++) {
    if (multi) info(`── ${relpath(files[i])} ──`);
    let code;
    try {
      code = await finishOne(client, files[i], tickets[i], s, seen);
    } catch (e) {
      if (!(e instanceof KaerisError)) throw e;
      refused(e);
      code = 1;
    }
    exitCode = Math.max(exitCode, code);
  }
  sayAbsentGlossary(seen, files);
  await showQuota(client);
  return exitCode;
}
