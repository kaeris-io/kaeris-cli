// The site link after a clean `kaeris check` (same rule as the Python package, tests/test_cta_links.py):
// every tenth clean run in a terminal; never in CI, with --json/--ci, into a pipe, or with KAERIS_NO_CTA=1.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { main } from "../src/cli.js";

const SITE = "https://kaeris.dev/?utm_source=cli";

function project() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kaeris-cta-"));
  fs.writeFileSync(path.join(dir, "en.json"), '{"a": "Hello {name}"}');
  fs.writeFileSync(path.join(dir, "de.json"), '{"a": "Hallo {name}"}');
  return dir;
}

// Runs main() in this process with stderr as a terminal (or not) and the cache in `dir`.
function runs(n, { tty = true, env = {}, extra = [], dir = project() } = {}) {
  const saved = { env: { ...process.env }, isTTY: process.stderr.isTTY, err: process.stderr.write, out: process.stdout.write };
  const results = [];
  try {
    for (const k of ["CI", "GITHUB_ACTIONS", "KAERIS_NO_CTA"]) delete process.env[k];
    Object.assign(process.env, { LOCALAPPDATA: path.join(dir, "cache"), XDG_CACHE_HOME: path.join(dir, "cache"), NO_COLOR: "1" }, env);
    Object.defineProperty(process.stderr, "isTTY", { value: tty, configurable: true, writable: true });
    for (let i = 0; i < n; i++) {
      let err = "";
      let out = "";
      process.stderr.write = (s) => { err += s; return true; };
      process.stdout.write = (s) => { out += s; return true; };
      const code = main(["check", "--source", path.join(dir, "en.json"), "--langs", "de", ...extra]);
      process.stderr.write = saved.err;
      process.stdout.write = saved.out;
      results.push({ code, err, out });
    }
  } finally {
    process.stderr.write = saved.err;
    process.stdout.write = saved.out;
    Object.defineProperty(process.stderr, "isTTY", { value: saved.isTTY, configurable: true, writable: true });
    for (const k of Object.keys(process.env)) if (!(k in saved.env)) delete process.env[k];
    Object.assign(process.env, saved.env);
  }
  return results;
}

test("every tenth clean run in a terminal names the site, on stderr", () => {
  const r = runs(20);
  assert.deepEqual(r.flatMap((x, i) => (x.err.includes(SITE) ? [i + 1] : [])), [10, 20]);
  for (const x of r) {
    assert.equal(x.code, 0);
    assert.ok(!x.out.includes("kaeris.dev"));
  }
});

test("never in CI", () => {
  assert.ok(!runs(10, { env: { CI: "true" } }).some((x) => x.err.includes(SITE)));
});

test("never with --ci", () => {
  assert.ok(!runs(10, { extra: ["--ci"] }).some((x) => x.err.includes(SITE)));
});

test("never into a pipe or a log", () => {
  assert.ok(!runs(10, { tty: false }).some((x) => x.err.includes(SITE)));
});

test("switched off with KAERIS_NO_CTA=1", () => {
  assert.ok(!runs(10, { env: { KAERIS_NO_CTA: "1" } }).some((x) => x.err.includes(SITE)));
});

test("never with --json, and stdout stays one JSON document", () => {
  for (const x of runs(10, { extra: ["--json"] })) {
    assert.ok(!(x.err + x.out).includes(SITE));
    JSON.parse(x.out);
  }
});

test("never after a failed check", () => {
  const dir = project();
  fs.writeFileSync(path.join(dir, "en.json"), '{"a": "Hello", "b": "Bye"}');
  fs.writeFileSync(path.join(dir, "de.json"), '{"a": "Hallo"}');
  const r = runs(10, { dir });
  assert.ok(r.every((x) => x.code === 1));
  assert.ok(!r.some((x) => x.err.includes(SITE)));
});
