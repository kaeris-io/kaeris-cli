// The `check` fix line of the JavaScript port, against the same pinned words as the Python
// original (cta_fix_cases.json, read by tests/test_check_fix_line.py too).
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { main } from "../src/cli.js";
import { fixCommand, fixLine, fixText, gapUnits } from "../src/cta.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const C = JSON.parse(fs.readFileSync(path.join(here, "cta_fix_cases.json"), "utf8"));
const asMap = (o) => new Map(Object.entries(o));
const CMD = "kaeris translate --langs de --only-new";

describe("check fix line: the same words as kaeris/cta.py", () => {
  test("units (code points, like the server)", () => {
    for (const c of C.units) assert.deepEqual(gapUnits(asMap(c.source), asMap(c.missing), c.incremental), c.want);
  });
  test("commands", () => {
    for (const c of C.commands) assert.equal(fixCommand(c.langs, { path: c.path, out: c.out, incremental: c.incremental }), c.want);
  });
  test("lines", () => {
    for (const c of C.lines) assert.equal(fixText(c.total, c.largest, CMD), c.want.replace("CMD", CMD).replace("URL", C.url));
  });
  test("this port names the Python package", () => {
    assert.ok(fixText(10, 10, CMD, { npm: true }).startsWith(C.npm_prefix + CMD + ","));
    assert.ok(fixLine(10, 10, CMD, { env: {}, isTTY: true }).startsWith(C.npm_prefix));
  });
  test("only for a person at a terminal", () => {
    assert.equal(fixLine(10, 10, CMD, { env: {}, isTTY: false }), null);
    assert.equal(fixLine(10, 10, CMD, { env: { CI: "true" }, isTTY: true }), null);
    assert.equal(fixLine(10, 10, CMD, { env: { KAERIS_NO_CTA: "1" }, isTTY: true }), null);
    assert.equal(fixLine(10, 10, CMD, { env: {}, isTTY: true, machine: true }), null);
    assert.equal(fixLine(10, 10, CMD, { env: {}, isTTY: true, ci: true }), null);
    assert.equal(fixLine(0, 0, CMD, { env: {}, isTTY: true }), null);
  });
});

describe("check fix line: the real command, not a terminal", () => {
  const run = promisify(execFile);
  const bin = path.join(here, "..", "bin", "kaeris.js");
  test("a pipe, --json and CI never get it", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kaeris-cta-"));
    try {
      fs.writeFileSync(path.join(dir, "en.json"), '{"a": "Hello", "b": "Bye"}');
      fs.writeFileSync(path.join(dir, "de.json"), '{"a": "Hallo"}');
      for (const [extra, env] of [[[], {}], [["--json"], {}], [[], { CI: "true" }]]) {
        const r = await run(process.execPath, [bin, "check", "--source", "en.json", "--langs", "de", ...extra],
          { cwd: dir, env: { ...process.env, ...env } }).catch((e) => e);
        assert.equal(r.code, 1);
        assert.ok(!(r.stdout + r.stderr).includes("utm_campaign"), r.stderr);
      }
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});

// main() in this process with stderr as a terminal (or not), as in cta.test.js.
function inTerminal({ tty = true, env = {}, extra = [] } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kaeris-fix-"));
  fs.writeFileSync(path.join(dir, "en.json"), '{"title": "Welcome, {name}", "cart": {"empty": "Your cart is empty"}, "checkout": "Checkout"}');
  fs.writeFileSync(path.join(dir, "de.json"), '{"title": "Willkommen, {name}"}');
  fs.writeFileSync(path.join(dir, "fr.json"), '{"title": "Bienvenue, {name}", "checkout": "Payer"}');
  const saved = { env: { ...process.env }, isTTY: process.stderr.isTTY, err: process.stderr.write, out: process.stdout.write, cwd: process.cwd() };
  let err = "";
  let out = "";
  let code;
  try {
    for (const k of ["CI", "GITHUB_ACTIONS", "KAERIS_NO_CTA"]) delete process.env[k];
    Object.assign(process.env, { NO_COLOR: "1" }, env);
    Object.defineProperty(process.stderr, "isTTY", { value: tty, configurable: true, writable: true });
    process.chdir(dir);
    process.stderr.write = (s) => { err += s; return true; };
    process.stdout.write = (s) => { out += s; return true; };
    code = main(["check", "--source", "en.json", "--langs", "de,fr", ...extra]);
  } finally {
    process.stderr.write = saved.err;
    process.stdout.write = saved.out;
    process.chdir(saved.cwd);
    Object.defineProperty(process.stderr, "isTTY", { value: saved.isTTY, configurable: true, writable: true });
    for (const k of Object.keys(process.env)) if (!(k in saved.env)) delete process.env[k];
    Object.assign(process.env, saved.env);
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return { code, err, out };
}

describe("check fix line: in a terminal, the way tests/test_check_fix_line.py runs it", () => {
  test("missing keys end with the fix, the same numbers as Python", () => {
    const r = inTerminal();
    assert.equal(r.code, 1);
    const last = r.err.trimEnd().split(/\r?\n/).at(-1);
    assert.equal(last, `${C.npm_prefix}kaeris translate en.json --langs de,fr --only-new, about 44 characters: within Free (1,500,000 a month with a free key). ${C.url}`);
    assert.ok(!r.out.includes("kaeris.dev"));
  });
  test("never with CI, --ci, --json, --sarif, a pipe, KAERIS_NO_CTA=1", () => {
    for (const opts of [{ env: { CI: "true" } }, { extra: ["--ci"] }, { extra: ["--json"] }, { extra: ["--sarif", "r.sarif"] }, { tty: false }, { env: { KAERIS_NO_CTA: "1" } }]) {
      const r = inTerminal(opts);
      assert.equal(r.code, 1);
      assert.ok(!(r.err + r.out).includes("utm_campaign"), JSON.stringify(opts));
    }
  });
});
