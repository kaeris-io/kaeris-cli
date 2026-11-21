// P0.2.47 step 2: the .po slots a Plural-Forms formula gives exactly one n (Python twin:
// tests/test_po_single_number_slots.py, kaeris/formats.single_number_slots).
import test from "node:test";
import assert from "node:assert/strict";
import { singleNumberSlots } from "../src/formats.js";

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

test("a formula that does not parse selects nothing", () => {
  assert.equal(singleNumberSlots(H("nplurals=2; plural=(n != 1;")), null);
  assert.equal(singleNumberSlots(H("nplurals=2; plural=n ? import os : 1;")), null);
  assert.equal(singleNumberSlots("Language: de\n"), null);
});
