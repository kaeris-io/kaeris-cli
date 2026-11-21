// P0.2.47 step 2: the .po slots a Plural-Forms formula gives exactly one n (Python twin:
// tests/test_po_single_number_slots.py, kaeris/formats.single_number_slots).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { singleNumberSlots, poLooseSlots, PLURAL_RULES } from "../src/formats.js";

const H = (rule) => `Plural-Forms: ${rule}\n`;
const sorted = (s) => (s === null ? null : [...s].sort((a, b) => a - b));

test("slots one number selects are found from the formula", () => {
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);"))), [0, 1, 2]);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"))), [0]);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;"))), [0]);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);"))), [0, 1]);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"))), []);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=4; plural=(n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3);"))), []);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=3; plural=(n%10==0 || (n%100>=11 && n%100<=19) ? 0 : n%10==1 && n%100!=11 ? 1 : 2);"))), []);
  assert.deepEqual(sorted(singleNumberSlots(H("nplurals=1; plural=0;"))), []);
});

test("loose slots need a valid formula that is the language's own (critic 21.11, B2)", () => {
  const AR = "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);";
  const PL = "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);";
  const CS = "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;";
  const HE = "nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);";
  const head = (lang, rule) => (lang ? `Language: ${lang}\n` : "") + `Plural-Forms: ${rule}\n`;
  const loose = (h, lang) => sorted(poLooseSlots(h, lang));
  assert.deepEqual(loose(head("ar", AR)), [0, 1, 2]);
  assert.deepEqual(loose(head("pl", PL)), [0]);
  assert.deepEqual(loose(head("he", HE)), [0, 1]);
  assert.deepEqual(loose(head("pt_PT", "nplurals=2; plural=(n != 1);")), [0]);
  assert.deepEqual(loose(head("pt_BR", "nplurals=2; plural=(n != 1);")), []);
  assert.deepEqual(loose(head("he", "nplurals=3; plural=n==1 ? 0 : (n==2 ? 1 : 2);")), [0, 1]);
  assert.deepEqual(loose(head("", AR), "ar"), [0, 1, 2]);
  assert.deepEqual(loose(head("ru", "nplurals=3; plural=n;")), []);
  assert.deepEqual(loose(head("he", "nplurals=2; plural=(n==1 ? 0 : n==2 ? 1 : 2);")), []);
  assert.equal(singleNumberSlots("Plural-Forms: nplurals=3; plural=n;\n"), null);
  assert.deepEqual(loose(head("ru", HE)), []);
  assert.deepEqual(loose(head("pl", CS)), []);
  assert.deepEqual(loose(head("xx", AR)), []);
  assert.deepEqual(loose(head("", AR)), []);
});

test("the gate table is the one the Python port has", () => {
  // kaeris/formats.py PLURAL_RULES, read as Python source: same rows, same formulas
  const py = readFileSync(new URL("../../kaeris/formats.py", import.meta.url), "utf8");
  const consts = Object.fromEntries([...py.matchAll(/^(_[A-Z_]+) = "([^"]+)"$/gm)].map((m) => [m[1], m[2]]));
  const block = py.slice(py.indexOf("PLURAL_RULES = {"), py.indexOf("}", py.indexOf("PLURAL_RULES = {")));
  const rows = {};
  for (const m of block.matchAll(/"([a-z-]+)": \((\d+), (?:"([^"]+)"|(_[A-Z_]+))\)/g)) {
    rows[m[1]] = [parseInt(m[2], 10), m[3] ?? consts[m[4]]];
  }
  assert.ok(Object.keys(rows).length >= 25, "parsed the Python table");
  assert.deepEqual(rows, { ...PLURAL_RULES });
});

test("a formula that does not parse selects nothing", () => {
  assert.equal(singleNumberSlots(H("nplurals=2; plural=(n != 1;")), null);
  assert.equal(singleNumberSlots(H("nplurals=2; plural=n ? import os : 1;")), null);
  assert.equal(singleNumberSlots("Language: de\n"), null);
});

// critic round 2: Language against --langs, formula limits — the same corpus and verdicts as the
// Python port (tests/test_po_single_number_slots.py reads this file too).
test("degenerate headers read as the Python port reads them", () => {
  const cases = JSON.parse(readFileSync(new URL("./po-degenerate.json", import.meta.url), "utf8"));
  assert.ok(cases.length >= 15);
  for (const c of cases) {
    assert.deepEqual(sorted(poLooseSlots(c.header, c.lang)), c.loose, c.name);
  }
});

test("a long formula is not evaluated", () => {
  const t = Date.now();
  assert.equal(singleNumberSlots(`Plural-Forms: nplurals=2; plural=(n != 1)${" + 0".repeat(10000)};\n`), null);
  assert.ok(Date.now() - t < 500);
});
