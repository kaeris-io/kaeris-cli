// Where a language's file is, for `check` (where to look) and `translate` (where to write):
// kaeris/cli.py _target_path, _existing_case, _out_path, _lproj_sibling, _canon_lang, _split_langs.
import fs from "node:fs";
import * as pp from "./pypath.js";
import { rx, strip } from "./py.js";
import { warn } from "./say.js";

// The "could not detect a layout" warning is said once per run; a command resets it.
export const layoutState = { warned: false };

// Xcode's own layout: en.lproj/Localizable.strings -> de.lproj/Localizable.strings.
export function lprojSibling(srcPath, lang, sourceLang, outDir) {
  const folder = pp.dirname(srcPath);
  if (pp.basename(folder) !== `${sourceLang}.lproj`) return null;
  return pp.join(outDir || pp.dirname(folder), `${lang}.lproj`, pp.basename(srcPath));
}

// The output path for `lang`'s translation of `srcPath`, mirroring common locale-file layouts.
export function targetPath(srcPath, lang, outDir, sourceLang) {
  const [stem, ext] = pp.splitext(pp.basename(srcPath));
  let srcDir = pp.dirname(srcPath);

  const parent = pp.basename(srcDir);
  if (ext.toLowerCase() === ".xml" && (parent === "values" || parent.startsWith("values-"))) {
    const resDir = outDir || pp.dirname(srcDir);
    return pp.join(resDir, `values-${lang}`, pp.basename(srcPath));
  }

  // Xcode keeps one folder per language (02.11: translate wrote en.lproj/de/ before this).
  const sibling = lprojSibling(srcPath, lang, sourceLang, outDir);
  if (sibling) return sibling;

  if (stem === sourceLang) {
    const d = outDir ? outDir : srcDir;
    return pp.join(d, `${lang}${ext}`);
  }

  if (pp.altsep) srcDir = srcDir.split(pp.altsep).join(pp.sep);
  const segs = srcDir ? srcDir.split(pp.sep) : [];
  let lastIdx = null;
  segs.forEach((seg, i) => {
    if (seg === sourceLang) lastIdx = i;
  });
  if (lastIdx !== null) {
    const newSegs = [...segs];
    newSegs[lastIdx] = lang;
    if (outDir) return pp.join(outDir, ...newSegs.slice(lastIdx), pp.basename(srcPath));
    return pp.join(newSegs.join(pp.sep), pp.basename(srcPath));
  }

  // Prefixed single-file convention: app_en.arb -> app_de.arb (Flutter), messages_en -> messages_de.
  if (stem.endsWith("_" + sourceLang) && stem.length > sourceLang.length + 1) {
    const prefix = stem.slice(0, -(sourceLang.length + 1));
    const d = outDir ? outDir : srcDir;
    return pp.join(d, `${prefix}_${lang}${ext}`);
  }

  if (!layoutState.warned) {
    warn(`Could not detect a known locale-file layout for '${srcPath}' (source_lang='${sourceLang}') — nesting output by language instead`);
    layoutState.warned = true;
  }
  const baseDir = outDir || srcDir;
  return pp.join(baseDir, lang, pp.basename(srcPath));
}

// A file or folder name as it is compared with a language code: lower case, `_` read as `-`.
const langFold = (text) => text.toLowerCase().replace(/_/g, "-");

// `path`, with each part that names `lang` spelled the way it already is on disk (zh-Hant.json
// next to a requested zh-hant.json, pt_BR.json for pt-BR). An exact match always wins.
export function existingCase(path, lang) {
  const [drive, rest] = pp.splitdrive(pp.normpath(path));
  const parts = rest.split(pp.sep);
  const want = langFold(lang);
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (!part || !langFold(part).includes(want)) continue;
    const parent = drive + (parts.slice(0, i).join(pp.sep) || (rest.startsWith(pp.sep) ? pp.sep : "."));
    let names;
    try {
      names = fs.readdirSync(parent);
    } catch {
      break;
    }
    if (names.includes(part)) continue;
    const same = names.filter((n) => langFold(n) === langFold(part));
    if (same.length === 1) parts[i] = same[0];
  }
  return drive + parts.join(pp.sep);
}

export const outPath = (srcPath, lang, outDir, sourceLang) => existingCase(targetPath(srcPath, lang, outDir, sourceLang), lang);

const LANG_TAG_RE = rx("^[A-Za-z]{2,3}(?:[-_](?:[A-Za-z]{2}|[A-Za-z]{4}|\\d{3}))*$");

// 'fr-ca' -> 'fr-CA', 'zh_hant' -> 'zh-Hant', 'PT-pt' -> 'pt-PT'. Anything that is not shaped like
// a language tag comes back as it was written, so it can be refused by name.
export function canonLang(tag) {
  tag = strip(String(tag));
  if (!LANG_TAG_RE.test(tag)) return tag;
  const [first, ...rest] = tag.split(/[-_]/);
  return [first.toLowerCase(), ...rest.map((p) => (p.length === 2 ? p.toUpperCase() : p.length === 4 ? p[0].toUpperCase() + p.slice(1).toLowerCase() : p))].join("-");
}

// 'fr-ca, pt_PT' (or a list from kaeris.json) -> ['fr-CA', 'pt-PT'], each language once.
export function splitLangs(raw) {
  const items = typeof raw === "string" ? raw.split(",") : Array.isArray(raw) ? raw : [];
  const result = [];
  for (const item of items) {
    const s = strip(String(item));
    if (s && !result.includes(canonLang(s))) result.push(canonLang(s));
  }
  return result;
}
