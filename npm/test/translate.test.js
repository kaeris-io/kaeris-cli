// `kaeris translate` against a stand-in for the KAERIS API: a small HTTP server inside this test,
// on 127.0.0.1. The real bin/kaeris.js runs as a child process, the way a person runs it.
import { test, describe, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const BIN = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "bin", "kaeris.js");

// ── a ZIP the way the server sends it ─────────────────────────────────────────

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// {name: string|Buffer} -> a ZIP; every other member deflated, the rest stored, as zipfile does.
function zip(members) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  Object.entries(members).forEach(([name, body], i) => {
    const data = Buffer.from(body);
    const method = i % 2 === 0 ? 8 : 0;
    const packed = method === 8 ? zlib.deflateRawSync(data) : data;
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6);
    local.writeUInt16LE(method, 8);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(packed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    locals.push(local, nameBuf, packed);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(method, 10);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(packed.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBuf);
    offset += 30 + nameBuf.length + packed.length;
  });
  const cd = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(centrals.length / 2, 8);
  end.writeUInt16LE(centrals.length / 2, 10);
  end.writeUInt32LE(cd.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, end]);
}

// ── the stand-in server ───────────────────────────────────────────────────────

const LANGUAGES = { en: "English", de: "German", fr: "French", "zh-Hant": "Chinese (Traditional)" };

// What each test wants the server to say. Reset before every run.
let scene;
const requests = [];

function defaultScene() {
  return {
    // POST /api/translate -> [status, body, headers]
    translate: () => [200, { job_id: "job1", edit_token: "tok1", warnings: [] }],
    status: () => [200, { status: "done", progress: 2, total: 2, current_lang: "de" }],
    members: { "de.json": "{}" },
    preview: () => [200, { _warnings: {}, _qa: {} }],
    receipt: () => [200, { model: "test-model", plan: "anonymous", strings: 3, seconds: 1, languages: { requested: ["de"], delivered: ["de"], failed: [] } }],
    keyInfo: () => [200, { tier: "anonymous", char_limit: 10000 }],
  };
}

function parseMultipart(body, ctype) {
  const boundary = /boundary=(.+)$/.exec(ctype)[1];
  const parts = {};
  const text = body.toString("latin1");
  for (const chunk of text.split("--" + boundary)) {
    const m = /^\r\nContent-Disposition: form-data; name="([^"]+)"(?:; filename="([^"]*)")?\r\n(?:Content-Type: [^\r]*\r\n)?\r\n([\s\S]*)\r\n$/.exec(chunk);
    if (!m) continue;
    parts[m[1]] = { filename: m[2], value: Buffer.from(m[3], "latin1") };
  }
  return parts;
}

function send(res, [code, body, headers = {}]) {
  const isBuf = Buffer.isBuffer(body);
  res.writeHead(code, { "Content-Type": isBuf ? "application/zip" : "application/json", ...headers });
  res.end(isBuf ? body : JSON.stringify(body));
}

let server;
let API;
before(async () => {
  server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const body = Buffer.concat(chunks);
      const rec = { method: req.method, url: req.url, headers: req.headers };
      if (req.method === "POST") rec.form = parseMultipart(body, req.headers["content-type"] || "");
      requests.push(rec);
      const u = req.url;
      if (u === "/api/languages") return send(res, [200, LANGUAGES]);
      if (u === "/api/config") return send(res, [200, { max_langs_anon: 8 }]);
      if (u === "/api/key/info") return send(res, scene.keyInfo());
      if (u === "/api/translate" && req.method === "POST") return send(res, scene.translate(rec));
      if (u.startsWith("/api/status/")) return send(res, scene.status());
      if (u.startsWith("/api/download/")) return send(res, [200, zip(scene.members)]);
      if (u.startsWith("/api/preview/")) return send(res, scene.preview());
      if (u.startsWith("/api/receipt/")) return send(res, scene.receipt());
      send(res, [404, { detail: "Not Found" }]);
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  API = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise((r) => server.close(r)));

// ── running the CLI ───────────────────────────────────────────────────────────

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "kaeris-tr-"));
}

function write(dir, rel, text) {
  const p = path.join(dir, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
  return p;
}

function kaeris(args, { cwd, env = {} } = {}) {
  requests.length = 0;
  const base = { ...process.env };
  delete base.KAERIS_API_KEY;
  delete base.KAERIS_OPENROUTER_KEY;
  delete base.KAERIS_API_URL;
  delete base.CI;
  return new Promise((resolve) => {
    execFile(process.execPath, [BIN, ...args], { cwd, env: { ...base, KAERIS_API_URL: API, NO_COLOR: "1", ...env }, timeout: 60000 },
      (error, stdout, stderr) => resolve({ code: error ? error.code : 0, stdout, stderr }));
  });
}

const posted = () => requests.filter((r) => r.method === "POST" && r.url === "/api/translate");

// ── the source the person has ─────────────────────────────────────────────────

const EN = `{
  "greeting": "Hello, {name}!",
  "items": "You have %s items in your cart",
  "buy_link": "See <a href=\\"/how-to-buy/\\">how to buy</a>",
  "docs": "Read the docs at https://example.com/docs/start"
}
`;
const DE = `{
  "greeting": "Hallo, {name}!",
  "items": "Sie haben %s Artikel im Warenkorb",
  "buy_link": "Siehe <a href=\\"/how-to-buy/\\">So kaufen Sie</a>",
  "docs": "Die Doku: https://example.com/docs/start"
}
`;
const FR = `{
  "greeting": "Bonjour, {name} !",
  "items": "Vous avez %s articles dans votre panier",
  "buy_link": "Voir <a href=\\"/how-to-buy/\\">comment acheter</a>",
  "docs": "La doc : https://example.com/docs/start"
}
`;

describe("translate: files land where the Python CLI puts them", () => {
  test("en.json -> de.json and fr.json beside it, bytes as the server sent them", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE, "fr.json": FR };
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de,fr"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "de.json"), "utf8"), DE);
    assert.equal(fs.readFileSync(path.join(dir, "fr.json"), "utf8"), FR);
    // Placeholders, the tag, the path and the URL are what the server returned.
    const de = JSON.parse(fs.readFileSync(path.join(dir, "de.json"), "utf8"));
    assert.match(de.greeting, /\{name\}/);
    assert.match(de.items, /%s/);
    assert.match(de.buy_link, /href="\/how-to-buy\/"/);
    assert.match(de.docs, /https:\/\/example\.com\/docs\/start/);
    // Written paths on stdout, one per line, like the Python CLI.
    assert.deepEqual(r.stdout.trim().split(/\r?\n/).map((p) => path.basename(p)).sort(), ["de.json", "fr.json"]);
    assert.match(r.stderr, /Wrote 2 file\(s\)/);
    assert.match(r.stderr, /no key: free demo limits 10,000 chars per file, 8 languages per run/);
  });

  test("the file goes to the server as it is on disk, with the languages", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE };
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--to", "de", "--keep", "KAERIS, GitHub", "--tone", "formal", "--context", "a shop"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    const [p] = posted();
    assert.equal(p.form.file.filename, "en.json");
    assert.equal(p.form.file.value.toString("utf8"), EN);
    assert.equal(p.form.languages.value.toString(), "de");
    assert.equal(p.form.glossary.value.toString(), "KAERIS,GitHub");
    assert.equal(p.form.tone.value.toString(), "formal");
    assert.equal(p.form.app_context.value.toString(), "a shop");
    assert.equal(p.headers["x-api-key"], undefined);
    assert.match(p.headers["user-agent"], /^kaeris-cli\//);
  });

  test("a key goes in X-API-Key, after the command or from the environment", async () => {
    scene = defaultScene();
    scene.keyInfo = () => [200, { tier: "premium" }];
    const dir = tmp();
    write(dir, "en.json", EN);
    let r = await kaeris(["translate", "en.json", "-l", "de", "--key", "k_test_1"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(posted()[0].headers["x-api-key"], "k_test_1");
    assert.doesNotMatch(r.stderr, /no key/);
    r = await kaeris(["translate", "en.json", "-l", "de"], { cwd: dir, env: { KAERIS_API_KEY: "k_test_2" } });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(posted()[0].headers["x-api-key"], "k_test_2");
  });

  test("en.lproj/Localizable.strings -> de.lproj/Localizable.strings", async () => {
    scene = defaultScene();
    const DE_STRINGS = '"greeting" = "Hallo, %@!";\n';
    scene.members = { "de.strings": DE_STRINGS };
    const dir = tmp();
    write(dir, "App/en.lproj/Localizable.strings", '"greeting" = "Hello, %@!";\n');
    const r = await kaeris(["translate", "App/en.lproj/Localizable.strings", "--langs", "de"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "App", "de.lproj", "Localizable.strings"), "utf8"), DE_STRINGS);
    assert.ok(!fs.existsSync(path.join(dir, "App", "en.lproj", "de")));
  });

  test("locales/en/common.json -> locales/de/common.json; --out moves the base", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE };
    const dir = tmp();
    write(dir, "locales/en/common.json", EN);
    let r = await kaeris(["translate", "locales/en/common.json", "--langs", "de"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "locales", "de", "common.json"), "utf8"), DE);
    write(dir, "en.json", EN);
    r = await kaeris(["translate", "en.json", "--langs", "de", "--out", "dist/i18n"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "dist", "i18n", "de.json"), "utf8"), DE);
  });

  test("Android res/values/strings.xml -> res/values-de/strings.xml", async () => {
    scene = defaultScene();
    const XML = '<resources><string name="hi">Hallo</string></resources>\n';
    scene.members = { "values-de/strings.xml": XML };
    const dir = tmp();
    write(dir, "res/values/strings.xml", '<resources><string name="hi">Hello</string></resources>\n');
    const r = await kaeris(["translate", "res/values/strings.xml", "--langs", "de"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "res", "values-de", "strings.xml"), "utf8"), XML);
  });

  test("kaeris.json gives the source and the languages", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE, "fr.json": FR };
    const dir = tmp();
    write(dir, "locales/en.json", EN);
    write(dir, "kaeris.json", JSON.stringify({ source: "locales/en.json", langs: ["de", "fr"], out: "locales" }));
    const r = await kaeris(["translate"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "locales", "fr.json"), "utf8"), FR);
    assert.match(r.stderr, /Using config: kaeris\.json/);
  });
});

describe("translate: refusals are one clear line and a non-zero exit", () => {
  const cases = [
    [401, { detail: "Invalid API key" }, /HTTP 401: Invalid API key/, /key/i],
    [402, { detail: "File exceeds free tier (12,000 chars; limit 10,000 on your plan)" }, /HTTP 402: File exceeds free tier/, /Limit reached\. Plans and limits: https:\/\/kaeris\.dev\/pricing\.html\?utm_source=cli/],
    [500, { detail: "Internal Server Error" }, /HTTP 500: Internal Server Error/, /try again/i],
    [503, "<html>bad gateway</html>", /HTTP 503/, /try again/i],
  ];
  for (const [code, body, said, next] of cases) {
    test(`HTTP ${code} on submit`, async () => {
      scene = defaultScene();
      scene.translate = () => [code, body];
      const dir = tmp();
      write(dir, "en.json", EN);
      const r = await kaeris(["translate", "en.json", "--langs", "de", ...(code === 401 ? ["--key", "bad"] : [])], { cwd: dir });
      assert.notEqual(r.code, 0);
      assert.match(r.stderr, said);
      assert.match(r.stderr, next);
      assert.doesNotMatch(r.stderr, /at .*\.js:\d+/); // no stack trace
      assert.ok(!fs.existsSync(path.join(dir, "de.json")));
    });
  }

  test("HTTP 429 is waited out, then refused by name", async () => {
    scene = defaultScene();
    let n = 0;
    scene.translate = () => (n++, [429, { detail: "Rate limit exceeded" }, { "Retry-After": "1" }]);
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de"], { cwd: dir });
    assert.notEqual(r.code, 0);
    assert.equal(n, 4); // the first try and three more, as the Python client
    assert.match(r.stderr, /HTTP 429: Rate limit exceeded/);
    assert.match(r.stderr, /still rate-limited/);
    assert.ok(!fs.existsSync(path.join(dir, "de.json")));
  });

  test("HTTP 429 once, then the job goes through", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE };
    let n = 0;
    scene.translate = () => (n++ === 0 ? [429, { detail: "slow down" }, { "Retry-After": "1" }] : [200, { job_id: "j2", edit_token: "t" }]);
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    assert.equal(fs.readFileSync(path.join(dir, "de.json"), "utf8"), DE);
  });

  test("a job that fails on the server", async () => {
    scene = defaultScene();
    scene.status = () => [200, { status: "error", error: "The model did not answer" }];
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de"], { cwd: dir });
    assert.notEqual(r.code, 0);
    assert.match(r.stderr, /The model did not answer/);
  });

  test("a language that fell back to the source exits 3", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE, "fr.json": EN };
    scene.status = () => [200, { status: "done", failed_langs: ["fr"] }];
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de,fr"], { cwd: dir });
    assert.equal(r.code, 3);
    assert.match(r.stderr, /1 language\(s\) fell back to source text \(not translated\): fr/);
  });

  test("an archive member that climbs out of the folder writes nothing", async () => {
    scene = defaultScene();
    scene.members = { "de.json": DE, "../evil.json": "{}" };
    const dir = tmp();
    write(dir, "sub/en.json", EN);
    const r = await kaeris(["translate", "sub/en.json", "--langs", "de"], { cwd: dir });
    assert.notEqual(r.code, 0);
    assert.match(r.stderr, /Refusing a result archive/);
    assert.ok(!fs.existsSync(path.join(dir, "evil.json")));
    assert.ok(!fs.existsSync(path.join(dir, "sub", "de.json")));
  });

  test("an unknown language is refused before anything is sent", async () => {
    scene = defaultScene();
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de,xx"], { cwd: dir });
    assert.equal(r.code, 1);
    assert.match(r.stderr, /Unknown language code: xx\. Codes offered: en, de, fr, zh-Hant/);
    assert.doesNotMatch(r.stderr, /kaeris languages/); // not in this package
    assert.equal(posted().length, 0);
  });

  test("http to a host that is not loopback is refused", async () => {
    scene = defaultScene();
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de"], { cwd: dir, env: { KAERIS_API_URL: "http://example.com" } });
    assert.equal(r.code, 2);
    assert.match(r.stderr, /must be https/);
  });

  test("no source, no languages", async () => {
    scene = defaultScene();
    const dir = tmp();
    let r = await kaeris(["translate", "--langs", "de"], { cwd: dir });
    assert.equal(r.code, 1);
    assert.match(r.stderr, /No source file given/);
    write(dir, "en.json", EN);
    r = await kaeris(["translate", "en.json"], { cwd: dir });
    assert.equal(r.code, 1);
    assert.match(r.stderr, /No target languages given/);
  });

  test("a flag of the Python package that is not here yet says so and sends nothing", async () => {
    scene = defaultScene();
    const dir = tmp();
    write(dir, "en.json", EN);
    for (const flag of ["--only-new", "--verify", "--dry-run"]) {
      const r = await kaeris(["translate", "en.json", "--langs", "de", flag], { cwd: dir });
      assert.equal(r.code, 2, flag);
      assert.match(r.stderr, new RegExp(`${flag} is not in the npm package yet`));
      assert.match(r.stderr, /pipx install kaeris/);
      assert.equal(posted().length, 0, flag);
    }
    write(dir, "kaeris.json", JSON.stringify({ source: "en.json", langs: ["de"], only_new: true }));
    const r = await kaeris(["translate"], { cwd: dir });
    assert.equal(r.code, 2);
    assert.match(r.stderr, /only_new/);
    assert.equal(posted().length, 0);
  });
});

describe("translate: glossary file", () => {
  test("kaeris-glossary.json: keep terms join --keep, the rest go as terms", async () => {
    scene = defaultScene();
    const dir = tmp();
    write(dir, "en.json", EN);
    write(dir, "kaeris-glossary.json", JSON.stringify({
      terms: [
        { term: "cart", translations: { de: "Warenkorb", fr: ["panier"] }, pos: "noun" },
        { term: "KAERIS", keep: true },
      ],
    }));
    const r = await kaeris(["translate", "en.json", "--langs", "de", "--keep", "GitHub"], { cwd: dir });
    assert.equal(r.code, 0, r.stderr);
    const [p] = posted();
    assert.equal(p.form.glossary.value.toString(), "GitHub,KAERIS");
    assert.deepEqual(JSON.parse(p.form.terms.value.toString("utf8")), [
      { term: "cart", translations: { de: ["Warenkorb"] }, pos: "noun" },
    ]);
    assert.match(r.stderr, /Glossary: 1 term\(s\), 1 kept as is/);
  });

  test("a named glossary file that is missing is an error", async () => {
    scene = defaultScene();
    const dir = tmp();
    write(dir, "en.json", EN);
    const r = await kaeris(["translate", "en.json", "--langs", "de", "--glossary-file", "nope.json"], { cwd: dir });
    assert.equal(r.code, 2);
    assert.match(r.stderr, /nope\.json: glossary file not found/);
  });
});

describe("translate: help", () => {
  test("translate --help names the flags", async () => {
    const r = await kaeris(["translate", "--help"], { cwd: tmp() });
    assert.equal(r.code, 0);
    assert.match(r.stdout, /usage: kaeris translate/);
    assert.match(r.stdout, /--langs, --to, -l LANGS/);
  });

  test("the main help no longer sends translate to Python", async () => {
    const r = await kaeris(["--help"], { cwd: tmp() });
    assert.match(r.stdout, /translate/);
    assert.doesNotMatch(r.stdout, /The other commands \(translate,/);
  });
});
