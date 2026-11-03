// The two `kaeris check` lines of kaeris/cta.py, the same rules and the same words:
// - after a clean run, the site link on every tenth clean run (the count lives in a local file;
//   a machine that cannot keep it never sees the line);
// - after missing keys, the command that fills them, about how many characters that is and which
//   plan covers it (npm/src/plans.js, generated from kaeris/plans.py). `translate` is in the Python
//   package, so this port names it.
// In a terminal only: never in CI, never with --json/--sarif/--ci, never into a pipe or a log,
// off with KAERIS_NO_CTA=1. Plain links with ?utm_source=cli: nothing is sent anywhere.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PLANS } from "./plans.js";

export const SITE_URL = "https://kaeris.dev/?utm_source=cli";
export const PRICING_URL = "https://kaeris.dev/pricing.html?utm_source=cli";
export const FIX_URL = `${PRICING_URL}&utm_campaign=check-fix`;
export const CHECK_LINE = `To translate new keys: kaeris translate, or ${SITE_URL}`;
export const CHECK_EVERY = 10;

export function disabled(env = process.env) {
  return !["", "0", "false", "no"].includes(String(env.KAERIS_NO_CTA ?? "").trim().toLowerCase());
}

// Where the Python package keeps its own small files (kaeris/updatecheck.py cache_dir).
export function cacheDir(env = process.env) {
  if (process.platform === "win32") {
    return path.join(env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "kaeris");
  }
  return path.join(env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"), "kaeris");
}

function quiet(env, isTTY, machine, ci) {
  return Boolean(machine || ci || env.CI || disabled(env) || !isTTY);
}

export function checkLine({ env = process.env, isTTY = process.stderr.isTTY, machine = false, ci = false, file } = {}) {
  try {
    if (quiet(env, isTTY, machine, ci)) return null;
    const p = file || path.join(cacheDir(env), "cta.json");
    let data = {};
    try {
      const parsed = JSON.parse(fs.readFileSync(p, "utf8"));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) data = parsed;
    } catch {
      data = {};
    }
    const prev = Number.isInteger(data.clean_checks) && data.clean_checks >= 0 ? data.clean_checks : 0;
    data.clean_checks = prev + 1;
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(data));
    return data.clean_checks % CHECK_EVERY === 0 ? CHECK_LINE : null;
  } catch {
    return null;
  }
}

// Python's len(): code points, the unit the server meters (a JS string counts UTF-16 units).
const chars = (s) => [...s].length;
const fmt = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");

const ORDER = ["free", "pro", "teamapi", "lifetime"];
const NAMES = { free: "Free", pro: "Pro", teamapi: "Team/API", lifetime: "Lifetime" };

function limits(tier, plans) {
  const p = plans[tier];
  if (tier === "free") return [p.month_with_key, p.file_with_key];
  return [p.month ?? null, p.file];
}

// [characters to translate, the largest single request] for the keys `check` found missing.
// `sourceFlat` is a Map (flattenAll), `missing` a Map lang -> keys.
export function gapUnits(sourceFlat, missing, incremental) {
  let whole = 0;
  for (const v of sourceFlat.values()) if (typeof v === "string") whole += chars(v);
  const perLang = [];
  for (const keys of missing.values()) {
    if (!keys || !keys.length) continue;
    let n = 0;
    if (incremental) {
      for (const k of keys) {
        const v = sourceFlat.get(k);
        if (typeof v === "string") n += chars(v);
      }
    } else n = whole;
    perLang.push(n); // metered without verify: the characters sent (kaeris/estimate.py)
  }
  if (!perLang.length) return [0, 0];
  return [perLang.reduce((a, b) => a + b, 0), incremental ? Math.max(...perLang) : whole];
}

export function fixCommand(langs, { path: file = null, out = null, incremental = true } = {}) {
  const q = (s) => (/[\s&|;<>()$`'"]/.test(s) ? `"${s}"` : s);
  const parts = ["kaeris translate"];
  if (file) parts.push(q(file));
  parts.push("--langs " + langs.join(","));
  if (out) parts.push("--out " + q(out));
  if (incremental) parts.push("--only-new");
  return parts.join(" ");
}

export function fixText(total, largest, command, { plans = PLANS, npm = false } = {}) {
  const head = (npm ? "Fix with the Python package (pipx install kaeris): " : "Fix: ") + command
    + `, about ${fmt(total)} characters`;
  let prev = null;
  let tier = null;
  for (const t of ORDER) {
    const [month, file] = limits(t, plans);
    if ((month === null || total <= month) && largest <= file) {
      tier = t;
      break;
    }
    prev = t;
  }
  if (tier === null) {
    const [, file] = limits("lifetime", plans);
    return `${head}: one request of ${fmt(largest)} characters is over the ${fmt(file)} per file of every plan, split the file. ${FIX_URL}`;
  }
  if (prev === null) return `${head}: within Free (${fmt(plans.free.month_with_key)} a month with a free key). ${FIX_URL}`;
  const [pmonth, pfile] = limits(prev, plans);
  const byMonth = pmonth !== null && total > pmonth;
  const why = byMonth ? `over ${NAMES[prev]}'s ${fmt(pmonth)} a month`
    : `one request of ${fmt(largest)} characters is over ${NAMES[prev]}'s ${fmt(pfile)} per file`;
  const life = `Lifetime $${plans.lifetime.price} once with your own OpenRouter key`;
  if (tier === "lifetime") return `${head}: ${why}; ${life} has no monthly limit. ${FIX_URL}`;
  const [month, file] = limits(tier, plans);
  const covers = byMonth ? `covers ${fmt(month)} a month` : `takes ${fmt(file)} per file`;
  return `${head}: ${why}; ${NAMES[tier]} $${plans[tier].price}/month ${covers}, or ${life}. ${FIX_URL}`;
}

export function fixLine(total, largest, command, { env = process.env, isTTY = process.stderr.isTTY, machine = false, ci = false } = {}) {
  try {
    if (total <= 0 || quiet(env, isTTY, machine, ci)) return null;
    return fixText(total, largest, command, { npm: true });
  } catch {
    return null;
  }
}
