// The npm port's plural tables are the server's (critic round 2, 21.11): held to the snapshot
// tests/data/server_plural_tables.json in this repository, written from backend/translator.py by
// tests/data/refresh_server_plural_tables.py. Python twin: tests/test_plural_tables_snapshot.py.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { PLURAL_RULES } from "../src/formats.js";
import { CLDR_REQUIRED, NO_SINGULAR, HAS_ONE } from "../src/detectors.js";

const SNAP = JSON.parse(readFileSync(new URL("../../tests/data/server_plural_tables.json", import.meta.url), "utf8"));
const sortedObj = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));

test("the gettext table is the server's snapshot", () => {
  assert.deepEqual(sortedObj({ ...PLURAL_RULES }), sortedObj(SNAP.PLURAL_RULES));
});

test("the CLDR tables are the server's snapshot", () => {
  const req = Object.fromEntries([...CLDR_REQUIRED].map(([k, v]) => [k, [...v].sort()]));
  assert.deepEqual(sortedObj(req), sortedObj(SNAP.CLDR_REQUIRED));
  assert.deepEqual([...NO_SINGULAR].sort(), SNAP.NO_SINGULAR);
  assert.deepEqual([...HAS_ONE].sort(), SNAP.HAS_ONE);
});
