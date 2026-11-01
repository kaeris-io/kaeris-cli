// The site link after a clean `kaeris check`, the same rule as kaeris/cta.py: every tenth clean
// run, in a terminal only. Never in CI, never with --json/--sarif/--ci, never into a pipe or a
// log, off with KAERIS_NO_CTA=1. A plain link with ?utm_source=cli: nothing is sent anywhere.
// The count lives in a local file; a machine that cannot keep it never sees the line.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const SITE_URL = "https://kaeris.dev/?utm_source=cli";
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

export function checkLine({ env = process.env, isTTY = process.stderr.isTTY, machine = false, ci = false, file } = {}) {
  try {
    if (machine || ci || env.CI || disabled(env) || !isTTY) return null;
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
