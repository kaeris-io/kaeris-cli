// kaeris-glossary.json for `translate`: reading it and what goes to the API (kaeris/glossary.py
// parse, load, find, Entry.renderings, Entry.for_api). The checks `check` runs against it are not
// here yet.
//
//   {"terms": [
//     {"term": "workspace", "translations": {"de": "Arbeitsbereich", "fr": ["espace de travail"]},
//      "case_sensitive": false, "pos": "noun", "note": "the shared project area"},
//     {"term": "KAERIS", "keep": true}
//   ]}
import { readText } from "./encoding.js";
import * as pp from "./pypath.js";

export const FILENAME = "kaeris-glossary.json";

export class GlossaryError extends Error {}

const base = (lang) => String(lang).replace(/_/g, "-").split("-")[0].toLowerCase();
const plen = (s) => [...s].length;

export class Entry {
  constructor(term, translations, caseSensitive = false, pos = "", note = "") {
    this.term = term;
    this.translations = translations; // [[lang as written, [rendering, …]], …]
    this.caseSensitive = caseSensitive;
    this.pos = pos;
    this.note = note;
  }

  // The accepted words for `lang`: its own entry (pt-BR, pt_br), else its language's (pt).
  renderings(lang) {
    const want = String(lang).replace(/_/g, "-").toLowerCase();
    for (const [name, words] of this.translations) if (name.replace(/_/g, "-").toLowerCase() === want) return [...words];
    for (const [name, words] of this.translations) if (name.replace(/_/g, "-").toLowerCase() === base(lang)) return [...words];
    return [];
  }

  forApi() {
    const out = { term: this.term, translations: Object.fromEntries(this.translations.map(([k, v]) => [k, [...v]])) };
    if (this.caseSensitive) out.case_sensitive = true;
    if (this.pos) out.pos = this.pos;
    if (this.note) out.note = this.note;
    return out;
  }
}

function text(value, what, where, limit) {
  if (typeof value !== "string" || !value.trim()) throw new GlossaryError(`${where}: ${what} must be a non-empty string`);
  value = value.trim().split(/\s+/).join(" ");
  if (plen(value) > limit) throw new GlossaryError(`${where}: ${what} is longer than ${limit} characters`);
  return value;
}

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// {entries, keep} from the file's JSON: {"terms": [...]} or the list itself.
export function parse(data) {
  const items = isObj(data) ? data.terms : data;
  if (!Array.isArray(items)) throw new GlossaryError('expected {"terms": [ … ]} or a list of terms');
  const entries = [];
  const keep = [];
  const seen = new Set();
  items.forEach((item, idx) => {
    let where = `term #${idx + 1}`;
    if (!isObj(item)) throw new GlossaryError(`${where}: expected an object with "term"`);
    const term = text(item.term, '"term"', where, 60);
    where = `term #${idx + 1} "${term}"`;
    const folded = term.toLowerCase();
    if (seen.has(folded)) throw new GlossaryError(`${where}: listed twice`);
    seen.add(folded);
    if (item.keep === true) {
      keep.push(term);
      return;
    }
    const cs = item.case_sensitive ?? false;
    if (typeof cs !== "boolean") throw new GlossaryError(`${where}: case_sensitive must be true or false`);
    const tr = item.translations;
    if (!isObj(tr) || !Object.keys(tr).length) {
      throw new GlossaryError(`${where}: "translations" must be an object like {"de": "Arbeitsbereich"} (or set "keep": true)`);
    }
    const translations = [];
    for (const [lang, raw] of Object.entries(tr)) {
      const words = Array.isArray(raw) ? raw : [raw];
      if (!words.length) throw new GlossaryError(`${where}: "translations" for ${lang} is empty`);
      translations.push([String(lang), words.map((w) => text(w, `"translations" for ${lang}`, where, 80))]);
    }
    const pos = item.pos ? text(item.pos, '"pos"', where, 20) : "";
    const note = item.note ? text(item.note, '"note"', where, 160) : "";
    entries.push(new Entry(term, translations, cs, pos, note));
  });
  return { entries, keep };
}

export function load(path) {
  let data;
  try {
    data = JSON.parse(readText(path));
  } catch (e) {
    if (e.code) throw new GlossaryError(`${path}: cannot read it (${e.message})`);
    throw new GlossaryError(`${path}: not valid JSON (${e.message})`);
  }
  try {
    return parse(data);
  } catch (e) {
    if (e instanceof GlossaryError) throw new GlossaryError(`${path}: ${e.message}`);
    throw e;
  }
}

// The glossary of this run: --glossary-file, else "glossary_file" in kaeris.json, else
// kaeris-glossary.json in the current folder. null when there is none. A file that was NAMED and
// is missing is an error; the default one is optional.
export function find(explicit, configPath) {
  const path = explicit || configPath;
  if (path) {
    if (!pp.isfile(path)) throw new GlossaryError(`${path}: glossary file not found`);
    return load(path);
  }
  if (pp.isfile(FILENAME)) return load(FILENAME);
  return null;
}

// `terms` for one job: each entry with only this job's languages, under the codes the job uses.
export function termsFor(glossary, langs) {
  if (!glossary) return [];
  const out = [];
  for (const e of glossary.entries) {
    const tr = {};
    for (const l of langs) {
      const r = e.renderings(l);
      if (r.length) tr[l] = r;
    }
    if (Object.keys(tr).length) out.push({ ...e.forApi(), translations: tr });
  }
  return out;
}
