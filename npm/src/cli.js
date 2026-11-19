// The `check` command: flags, kaeris.json, how a source file finds its translations, the report,
// and the exit code (0 clean, 1 a problem was found, 2 bad usage or an unreadable file).
import { checkLocales } from "./check.js";
import { checkLine, fixCommand, fixLine, gapUnits } from "./cta.js";
import { flattenAll } from "./flatten.js";
import { readText, UnknownEncoding } from "./encoding.js";
import { ValueError } from "./errors.js";
import * as fm from "./formats.js";
import { dumps, parse as parseJson } from "./json.js";
import { reprList, strip } from "./py.js";
import * as pp from "./pypath.js";
import { TooDeep } from "./flatten.js";
import * as sarif from "./sarif.js";
import { version } from "./version.js";
import { info, ok, warn, err, out } from "./say.js";
import { layoutState, lprojSibling, outPath, splitLangs } from "./layout.js";
import { cmdTranslate, TRANSLATE_OPTIONS, TRANSLATE_HELP } from "./translate.js";

const CONFIG_FILENAME = "kaeris.json";

class KaerisError extends Error {}

// ── arguments, the way argparse reads them ────────────────────────────────────

const PYPI_COMMANDS = ["fix", "languages", "init", "quota"];
const COMMANDS = ["check", "translate", ...PYPI_COMMANDS];

const GLOBAL_OPTIONS = [
  { long: "--version", flag: true },
  { long: "--api-url", value: true },
  { long: "--key", short: "-k", value: true },
  { long: "--openrouter-key", value: true },
  { long: "--config", value: true },
  { long: "--help", short: "-h", flag: true },
];

const CHECK_OPTIONS = [
  { long: "--source", value: true },
  { long: "--langs", short: "-l", value: true },
  { long: "--out", short: "-o", value: true },
  { long: "--pattern", value: true },
  { long: "--glossary", value: true },
  { long: "--keep", value: true, dest: "glossary" },
  { long: "--strict", flag: true },
  { long: "--json", flag: true },
  { long: "--sarif", value: true },
  { long: "--ci", flag: true },
  { long: "--help", short: "-h", flag: true },
];

class UsageError extends Error {}

// Longest unambiguous prefix wins, as in argparse. `translate` takes exact names only, as the
// Python package does since `--to de,fr` was read as `--tone` (newcomer run, 03.11).
function findOption(options, token, exactOnly = false) {
  const exact = options.find((o) => o.long === token || o.short === token || (o.aliases || []).includes(token));
  if (exact) return exact;
  if (token.startsWith("--") && !exactOnly) {
    const hits = options.filter((o) => o.long.startsWith(token));
    if (hits.length === 1) return hits[0];
    if (hits.length > 1) throw new UsageError(`ambiguous option: ${token} could match ${hits.map((h) => h.long).join(", ")}`);
  }
  return null;
}

// Reads options out of argv until a non-option (the command) when `stopAtPositional`.
function readOptions(options, argv, start, stopAtPositional, exactOnly = false) {
  const values = {};
  const positional = [];
  const unknown = [];
  let i = start;
  for (; i < argv.length; i++) {
    const tok = argv[i];
    if (tok === "--") {
      positional.push(...argv.slice(i + 1));
      i = argv.length;
      break;
    }
    if (!tok.startsWith("-") || tok === "-") {
      if (stopAtPositional) break;
      positional.push(tok);
      continue;
    }
    let name = tok;
    let inline = null;
    if (tok.startsWith("--") && tok.includes("=")) {
      name = tok.slice(0, tok.indexOf("="));
      inline = tok.slice(tok.indexOf("=") + 1);
    } else if (!tok.startsWith("--") && tok.length > 2) {
      name = tok.slice(0, 2);
      inline = tok.slice(2);
    }
    const opt = findOption(options, name, exactOnly);
    if (!opt) {
      unknown.push(tok);
      continue;
    }
    const dest = opt.dest ?? opt.long.slice(2).replace(/-/g, "_");
    if (opt.flag) {
      if (inline !== null && tok.startsWith("--")) throw new UsageError(`argument ${opt.long}: ignored explicit argument '${inline}'`);
      values[dest] = opt.const !== undefined ? opt.const : true;
      if (opt.unsupported) (values._unsupported ||= []).push(opt.long);
    } else {
      let v = inline;
      if (v === null) {
        const next = argv[i + 1];
        if (next === undefined || (next.startsWith("-") && next !== "-" && !/^-\d/.test(next))) throw new UsageError(`argument ${opt.short ? `${opt.short}/` : ""}${opt.long}: expected one argument`);
        v = next;
        i++;
      }
      values[dest] = v;
      if (opt.unsupported) (values._unsupported ||= []).push(opt.long);
    }
  }
  return { values, positional, unknown, next: i };
}

const CHECK_USAGE =
  "usage: kaeris check [-h] [--source SOURCE] [--langs LANGS] [--out OUT] [--pattern PATTERN]\n" +
  "                    [--glossary GLOSSARY] [--strict] [--json] [--sarif PATH] [--ci]";

const CHECK_HELP = `${CHECK_USAGE}

Static, local, no-API check: compares the source (base-language) file against each target
locale file and reports missing keys, placeholder mismatches ({name}, %s, %d, {{x}}, ICU
{count, plural, ...}) and translation faults. Exits non-zero so it can gate a CI merge.
Reads ./kaeris.json for source/langs/out when flags are omitted.

options:
  -h, --help            show this help message and exit
  --source SOURCE       Source (base-language) file in any format \`translate\` takes (${fm.SUPPORTED_TEXT});
                        optional if 'source' is set in kaeris.json
  --langs, -l LANGS     Comma-separated target languages, e.g. es,fr,de; optional if 'langs' is
                        set in kaeris.json
  --out, -o OUT         Directory containing target locale files (default: where \`translate\`
                        writes them, next to the source, or 'out' in kaeris.json)
  --pattern PATTERN     Target filename pattern, '{lang}' is replaced with the language code
                        (default: the layout \`translate\` writes, e.g. de.json, app_de.arb,
                        values-de/strings.xml)
  --glossary, --keep GLOSSARY
                        Comma-separated terms the translation must keep verbatim, e.g.
                        --glossary 'KAERIS,GitHub' (default: 'keep' in kaeris.json). A target
                        that dropped one fails the check.
  --strict              Also fail (non-zero exit) if a target has extra/stale keys not in the
                        source, or any warning
  --json                Machine-readable JSON output instead of the human report
  --sarif PATH          Also write a SARIF 2.1.0 report to PATH, for github/codeql-action/upload-sarif
  --ci                  Same check and exit code as plain \`check\`: the exit code already gates a
                        merge (0 clean, 1 missing/placeholder problem found, 2 bad usage); the
                        occasional site link after a clean run is never printed with it
`;

const MAIN_USAGE = "usage: kaeris [-h] [--version] [--config CONFIG] {check,translate,fix,languages,init,quota} ...";

const MAIN_HELP = `${MAIN_USAGE}

commands:
  check      Compare a source locale file with its translations; fails CI when keys are
             missing or placeholders are broken, and on extra keys and warnings (such as
             text left untranslated) with --strict. Offline.
  translate  Translate a strings file through the KAERIS API and write the translations
             next to it. Without a key it runs as the free demo with smaller limits.

fix, languages, init and quota are in the Python package: pipx install kaeris

options:
  -h, --help       show this help message and exit
  --version        show the version and exit
  --config CONFIG  Path to a config file (default: ./${CONFIG_FILENAME} if present). CLI flags
                   override the config.
`;

// ── configuration ─────────────────────────────────────────────────────────────

// kaeris.json (explicit --config PATH, else ./kaeris.json if present). Comment keys ("//", "_...")
// are ignored.
function loadConfig(explicit) {
  const path = explicit || (pp.isfile(CONFIG_FILENAME) ? CONFIG_FILENAME : null);
  if (!path) return [new Map(), null];
  if (!pp.isfile(path)) throw new KaerisError(`Config file not found: ${path}`);
  let raw;
  try {
    raw = parseJson(readText(path));
  } catch (e) {
    if (e instanceof ValueError) throw new KaerisError(`Invalid JSON in ${path}: ${e.message}`);
    throw e;
  }
  if (!(raw instanceof Map)) throw new KaerisError(`Invalid config in ${path}: expected a JSON object`);
  const cfg = new Map([...raw].filter(([k]) => !k.startsWith("//") && !k.startsWith("_")));
  return [cfg, path];
}

const truthy = (v) => (v instanceof Map ? v.size > 0 : Array.isArray(v) ? v.length > 0 : Boolean(v));
const cfgGet = (cfg, k) => (cfg.has(k) ? cfg.get(k) : undefined);

// ── where the translations are ────────────────────────────────────────────────

class BadTarget extends Error {}

// Encoding is not syntax: without this a person goes hunting for a broken bracket in a file that
// is intact — it is just not saved as UTF-8.
const hint = (e) => (e instanceof UnknownEncoding ? " — save it as UTF-8 (or UTF-16 with a byte-order mark)" : "");

// Expand a glob pattern in a source path to a single file, if any glob characters are present.
function resolveSource(rawPath) {
  if (!/[*?[]/.test(rawPath)) return rawPath;
  const matches = pp.glob(rawPath).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  if (!matches.length) return null;
  if (matches.length > 1) warn(`Multiple files match '${rawPath}' — using ${matches[0]} (others: ${matches.slice(1).join(", ")})`);
  return matches[0];
}

// Where target files are, and language codes: ./layout.js (shared with `translate`).

// A String Catalog's synthetic sub-keys, readable: `cart⟦sub:count⟧⟦plural⟧` -> `cart (sub count, plural)`.
const XC_MARKER_RE = /((?:⟦[^⟦⟧]*⟧)+)/g;

function prettyKey(text) {
  if (!text || !text.includes("⟦")) return text;
  return text.replace(XC_MARKER_RE, (_, group) => {
    const parts = group.slice(1, -1).split("⟧⟦").filter(Boolean);
    return " (" + parts.map((p) => p.replace(/:/g, " ")).join(", ") + ")";
  });
}

const plural = (n, one, many) => (n !== 1 ? many : one);

// ── the command ───────────────────────────────────────────────────────────────

function stripArbMeta(obj) {
  if (obj instanceof Map) return new Map([...obj].filter(([k]) => !String(k).startsWith("@")));
  return obj;
}

function cmdCheck(args, globals) {
  let config;
  let configPath;
  try {
    [config, configPath] = loadConfig(globals.config);
  } catch (e) {
    if (e instanceof KaerisError) {
      err(e.message);
      return 2;
    }
    throw e;
  }
  if (configPath && !args.json) info(`Using config: ${configPath}`);

  const rawPath = args.source || cfgGet(config, "source");
  if (!rawPath) {
    err("No source file given (--source PATH, or 'source' in kaeris.json)");
    return 2;
  }
  const path = typeof rawPath === "string" ? resolveSource(rawPath) : null;
  if (!path || !pp.isfile(path)) {
    err(`Source file not found: ${path || rawPath}`);
    return 2;
  }
  const kind = fm.kindOf(path);
  if (kind === null) {
    err(`kaeris check reads ${fm.SUPPORTED_TEXT} (got ${path})`);
    return 2;
  }
  const isArb = kind === "arb";
  const merged = fm.MERGED.includes(kind);
  const jsonLike = kind === "json" || kind === "arb";

  const langs = splitLangs(args.langs ? args.langs : cfgGet(config, "langs"));
  if (!langs.length) {
    err("No target languages given (--langs es,fr,de, or 'langs' in kaeris.json)");
    return 2;
  }

  // null means "where `translate` writes by default": the source's own folder layout decides
  // (res/values -> res/values-<lang>, locales/en -> locales/<lang>).
  const outDirRaw = args.out || cfgGet(config, "out") || null;
  const outDir = typeof outDirRaw === "string" ? outDirRaw : null;
  let sourceLang = cfgGet(config, "source_lang") || "en";
  layoutState.warned = false; // warn at most once per check run

  const resolveTarget = (lang) => {
    if (args.pattern) {
      return pp.join(outDir || pp.dirname(pp.abspath(path)), args.pattern.replace(/\{lang\}/g, lang));
    }
    // Xcode keeps one folder per language. Asked first: the generic layout lookup warns
    // "no known layout" for it.
    const sibling = lprojSibling(path, lang, sourceLang, outDir);
    if (sibling && pp.isfile(sibling)) return sibling;
    return outPath(path, lang, outDir, sourceLang);
  };

  // One file holds the source AND every language (a String Catalog, a CSV with a column per
  // language): there is no per-language file to resolve.
  let byLang = null;
  let sourceObj;
  try {
    if (merged) {
      let fileLang;
      [fileLang, byLang] = fm.readMerged(path);
      sourceLang = cfgGet(config, "source_lang") || fileLang;
      sourceObj = fm.findLang(byLang, sourceLang) || new Map();
      if (!sourceObj.size) {
        err(`No strings for the source language '${sourceLang}' in ${path}`);
        return 2;
      }
      if (kind === "csv") {
        // `translate` writes the CSV with its language columns beside the source, in a folder of
        // its own (translations/<name>.csv): read those columns too.
        layoutState.warned = true;
        const written = outPath(path, "translations", outDir, sourceLang);
        if (pp.isfile(written) && pp.abspath(written) !== pp.abspath(path)) byLang = new Map([...byLang, ...fm.readMerged(written)[1]]);
      }
    } else if (jsonLike) {
      sourceObj = parseJson(readText(path));
      if (!(sourceObj instanceof Map)) {
        err(`Invalid source file ${path}: expected a JSON object`);
        return 2;
      }
      if (isArb) sourceObj = stripArbMeta(sourceObj);
    } else {
      sourceObj = fm.readOne(path, "source");
      if (!sourceObj.size) {
        err(`No translatable strings found in ${path}`);
        return 2;
      }
    }
  } catch (e) {
    if (e instanceof ValueError || e.code) {
      const what = kind === "xcstrings" ? "String Catalog" : "source file";
      err(`Could not read ${what} ${path}: ${e.code ? osMessage(e) : e.message}${hint(e)}`);
      return 2;
    }
    throw e;
  }
  if (!args.json) for (const note of sourceObj.notes ?? []) warn(`${path}: ${note.msg}`);

  const loadTarget = (lang) => {
    if (merged) {
      // Absent from the file is the same as an absent file: every key is missing.
      return fm.findLang(byLang, lang);
    }
    const targetFile = resolveTarget(lang);
    if (!pp.isfile(targetFile)) return null;
    if (!jsonLike) {
      let obj;
      try {
        obj = fm.readOne(targetFile, "target", lang);
      } catch (e) {
        if (e instanceof ValueError || e.code) throw new BadTarget(`${lang}: could not parse ${targetFile}: ${e.code ? osMessage(e) : e.message}${hint(e)}`);
        throw e;
      }
      if (kind === "markdown" && obj.size !== sourceObj.size) {
        // A document has no keys: its blocks are paired by position, so a block added, merged or
        // lost anywhere shifts every one after it.
        obj.skipPairwise = true;
        obj.notes.push({
          key: "", severity: "error",
          msg: `${obj.size} translatable blocks, the source has ${sourceObj.size}: a heading, paragraph, list item or table cell was added, merged or lost`,
        });
      }
      return obj;
    }
    let obj;
    try {
      obj = parseJson(readText(targetFile));
    } catch (e) {
      if (e instanceof ValueError || e.code) throw new BadTarget(`${lang}: could not parse ${targetFile}: ${e.code ? osMessage(e) : e.message}${hint(e)}`);
      throw e;
    }
    if (!(obj instanceof Map)) throw new BadTarget(`${lang}: ${targetFile} is not a JSON object`);
    return isArb ? stripArbMeta(obj) : obj;
  };

  // "keep" is the documented key `kaeris init` writes; flag wins, then either config key.
  let glossary;
  if (args.glossary) glossary = args.glossary.split(",").map((t) => strip(t)).filter(Boolean);
  else {
    const g = cfgGet(config, "keep");
    const g2 = cfgGet(config, "glossary");
    glossary = truthy(g) ? g : truthy(g2) ? g2 : null;
    if (Array.isArray(glossary)) glossary = glossary.filter((t) => typeof t === "string");
    else if (glossary !== null) glossary = null;
  }
  let result;
  try {
    result = checkLocales(sourceObj, langs, loadTarget, glossary);
  } catch (e) {
    if (e instanceof BadTarget) {
      err(e.message);
      return 2;
    }
    throw e;
  }

  if (args.sarif) {
    // Written even when nothing is wrong: upload-sarif fails a workflow if the file is missing.
    try {
      sarif.write(args.sarif, sarif.build(result, path, resolveTarget, process.cwd()));
      if (!args.json) info(`SARIF report → ${args.sarif}`);
    } catch (e) {
      if (!e.code) throw e;
      warn(`Could not write SARIF report to ${args.sarif}: ${osMessage(e)}`);
    }
  }

  const faults = result.faults;
  const warnings = result.warnings;
  const sum = (m) => [...m.values()].reduce((n, v) => n + v.length, 0);
  const nMissing = sum(result.missing);
  const nExtra = sum(result.extra);
  const nPh = result.placeholder_issues.length;
  const nFaults = faults.length;
  const nWarn = warnings.length;
  // RED (missing / placeholder mismatch / detector fault) already flips result.ok. --strict
  // escalates the soft signals (extra/stale keys, YELLOW warnings) to a failure.
  const fail = !result.ok || (args.strict && (nExtra || nWarn));

  if (!args.json) {
    for (const lang of langs) {
      if (result.missing_files.includes(lang)) {
        err(merged ? `${lang}: no translations in ${path}` : `${lang}: locale file not found (${resolveTarget(lang)})`);
        continue;
      }
      const missing = result.missing.get(lang) || [];
      const extra = result.extra.get(lang) || [];
      const issues = result.placeholder_issues.filter((i) => i.lang === lang);
      const langFaults = faults.filter((f) => f.lang === lang);
      const langWarns = warnings.filter((w) => w.lang === lang);
      if (!missing.length && !extra.length && !issues.length && !langFaults.length && !langWarns.length) {
        ok(`${lang}: complete & placeholder-safe`);
        continue;
      }
      if (missing.length)
        err(`${lang}: ${missing.length} missing key(s): ${missing.slice(0, 10).map(prettyKey).join(", ")}${missing.length > 10 ? " ..." : ""}`);
      if (issues.length) {
        err(`${lang}: ${issues.length} placeholder mismatch(es):`);
        for (const i of issues)
          out(prettyKey(`    ${i.key}: missing ${i.missing.length ? reprList(i.missing) : "-"}, added ${i.added.length ? reprList(i.added) : "-"}`));
      }
      if (langFaults.length) {
        err(`${lang}: ${langFaults.length} translation fault(s):`);
        for (const f of langFaults) out(prettyKey(f.key ? `    ${f.key}: ${f.msg}` : `    ${f.msg}`));
      }
      if (langWarns.length) {
        (args.strict ? err : warn)(`${lang}: ${langWarns.length} warning(s):`);
        for (const w of langWarns) out(prettyKey(`    ${w.key ?? ""}: ${w.msg}`.trimEnd()));
      }
      if (extra.length)
        (args.strict ? err : warn)(`${lang}: ${extra.length} extra/stale key(s): ${extra.slice(0, 10).map(prettyKey).join(", ")}${extra.length > 10 ? " ..." : ""}`);
    }

    if (fail) {
      const parts = [];
      if (nMissing) parts.push(`${nMissing} missing ${plural(nMissing, "key", "keys")}`);
      if (nPh) parts.push(`${nPh} placeholder ${plural(nPh, "mismatch", "mismatches")}`);
      if (nFaults) parts.push(`${nFaults} translation ${plural(nFaults, "fault", "faults")}`);
      if (args.strict && nWarn) parts.push(`${nWarn} ${plural(nWarn, "warning", "warnings")} (--strict)`);
      if (args.strict && nExtra) parts.push(`${nExtra} extra ${plural(nExtra, "key", "keys")} (--strict)`);
      err(parts.join(", "));
      if (nMissing) {
        // The command that fills the gaps, about how many characters and which plan covers it.
        const missing = new Map([...result.missing].filter(([, keys]) => keys && keys.length));
        const incremental = jsonLike && !merged;
        const [total, largest] = gapUnits(flattenAll(sourceObj), missing, incremental);
        const cmd = fixCommand([...missing.keys()], { path: args.source || null, out: args.out || null, incremental });
        const line = fixLine(total, largest, cmd, { machine: Boolean(args.sarif), ci: Boolean(args.ci) });
        if (line) out(line);
      }
    } else if (nWarn) warn(`${nWarn} warning(s) — non-blocking (use --strict to fail on them)`);
    else {
      ok("all locales complete & placeholder-safe");
      const line = checkLine({ machine: Boolean(args.sarif), ci: Boolean(args.ci) });
      if (line) out(line);
    }
  }

  if (args.json) process.stdout.write(dumps(result, 2, false) + "\n");

  return fail ? 1 : 0;
}

// Node's file-system error in the words Python's OSError uses: [Errno N] reason: 'path'
const ERRNO = { ENOENT: [2, "No such file or directory"], EACCES: [13, "Permission denied"], EISDIR: [21, "Is a directory"], EPERM: [1, "Operation not permitted"] };
function osMessage(e) {
  const [n, text] = ERRNO[e.code] ?? [0, e.message];
  return `[Errno ${n}] ${text}${e.path ? `: '${e.path}'` : ""}`;
}

// ── entry point ───────────────────────────────────────────────────────────────

export function main(argv) {
  try {
    const g = readOptions(GLOBAL_OPTIONS, argv, 0, true);
    if (g.unknown.length && !g.values.help) throw new UsageError(`unrecognized arguments: ${g.unknown.join(" ")}`);
    if (g.values.version) {
      process.stdout.write(`kaeris ${version}\n`);
      return 0;
    }
    const command = argv[g.next];
    if (g.values.help || command === undefined) {
      const stream = g.values.help ? process.stdout : process.stdout;
      stream.write(MAIN_HELP);
      return g.values.help ? 0 : 1;
    }
    if (!COMMANDS.includes(command)) {
      throw new UsageError(`argument command: invalid choice: '${command}' (choose from ${COMMANDS.map((c) => `'${c}'`).join(", ")})`);
    }
    if (command === "translate") {
      const t = readOptions(TRANSLATE_OPTIONS, argv, g.next + 1, false, true);
      if (t.values.help) {
        process.stdout.write(TRANSLATE_HELP);
        return 0;
      }
      if (t.unknown.length) throw new UsageError(`unrecognized arguments: ${t.unknown.join(" ")}`);
      return cmdTranslate({ ...t.values, files: t.positional }, g.values, loadConfig).catch((e) => {
        if (e instanceof KaerisError || e instanceof TooDeep) {
          err(e.message);
          return 2;
        }
        err(`kaeris translate stopped on an internal error: ${e && e.message ? e.message : e}`);
        if (process.env.KAERIS_DEBUG && e && e.stack) out(e.stack);
        return 2;
      });
    }
    if (command !== "check") {
      err(`kaeris ${command} is not in this package: it needs the Python version, which has fix, languages, init and quota. Install it with: pipx install kaeris`);
      return 2;
    }
    const c = readOptions(CHECK_OPTIONS, argv, g.next + 1, false);
    if (c.values.help) {
      process.stdout.write(CHECK_HELP);
      return 0;
    }
    const extra = [...c.unknown, ...c.positional];
    if (extra.length) throw new UsageError(`unrecognized arguments: ${extra.join(" ")}`);
    return cmdCheck(c.values, g.values);
  } catch (e) {
    if (e instanceof UsageError) {
      process.stderr.write(`${MAIN_USAGE}\nkaeris: error: ${e.message}\n`);
      return 2;
    }
    if (e instanceof KaerisError || e instanceof TooDeep) {
      err(e.message);
      return 2;
    }
    throw e;
  }
}
