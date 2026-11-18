// The KAERIS API client of kaeris/client.py, on Node's built-in fetch: the same calls, the same
// guards (https only, a redirect never leaves the host, archive member names checked), the same
// retries (a 429 waited out, a refused connection tried again, a dropped one never re-sent).
import crypto from "node:crypto";
import { readZip, BadZip } from "./zip.js";
import { version } from "./version.js";

export const DEFAULT_API = "https://kaeris.dev";

export class KaerisError extends Error {
  constructor(message, code = null) {
    super(message);
    this.code = code;
  }
}

// The job died with the server process that ran it; the server returned its quota, so sending it
// again is not a second charge.
export class KaerisInterrupted extends KaerisError {}

const RESTART_PHRASE = "the server process restarted";

// A key ready for an HTTP header, or a refusal that never contains the key.
export function checkedKey(key, label) {
  if (key === undefined || key === null) return null;
  const cleaned = String(key).trim();
  if (!cleaned) return null;
  for (const ch of cleaned) {
    const c = ch.codePointAt(0);
    if (c < 32 || c >= 127) {
      throw new KaerisError(
        `This ${label} contains characters that cannot be sent in an HTTP header (non-ASCII or control characters). Check it was copied whole and without invisible characters.`,
      );
    }
  }
  return cleaned;
}

// https, or http to loopback only: over http the key and the strings travel in the clear.
export function checkedApiUrl(url) {
  const raw = String(url || "").trim().replace(/\/+$/, "");
  if (!raw) throw new KaerisError("Empty API URL");
  const full = raw.includes("://") ? raw : "https://" + raw;
  let parsed;
  try {
    parsed = new URL(full);
  } catch {
    throw new KaerisError(`Refusing to use ${raw}: not a URL`);
  }
  const host = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (parsed.protocol === "https:") return full;
  const loopback = host === "localhost" || host === "::1" || host.startsWith("127.");
  if (parsed.protocol === "http:" && loopback) return raw;
  throw new KaerisError(
    `Refusing to use ${raw}: an API URL must be https — over http your API key and the strings you translate travel in the clear. (http is allowed for localhost only.)`,
  );
}

// One directory level is legitimate (values-de/strings.xml); nothing may climb out of the folder.
export const MAX_MEMBER_DEPTH = 2;

export function safeMemberName(name) {
  const raw = String(name).replace(/\\/g, "/");
  const parts = raw.split("/").filter((p) => p !== "" && p !== ".");
  const bad = !parts.length || raw.startsWith("/") || parts.includes("..") || (raw.length > 1 && raw[1] === ":") || parts.length > MAX_MEMBER_DEPTH;
  if (bad) {
    throw new KaerisError(
      `Refusing a result archive: the member name '${name}' would write outside the output directory. Nothing was written.`,
    );
  }
  return parts.join("/");
}

export const SUBMIT_RETRIES = 3;
export const RECEIPT_RETRIES = 10;
export const MAX_RETRY_WAIT = 60;
export const READ_RETRIES = 5;
export const NET_RETRIES = 5;
export const NET_MAX_WAIT = 30;
const POLL_SLOWDOWN = 2.0;
const MAX_POLL_SLOWDOWN = 8.0;
const MAX_REDIRECTS = 5;

const DROPPED = new Set([
  "ECONNRESET", "ECONNABORTED", "EPIPE", "ETIMEDOUT", "UND_ERR_SOCKET", "UND_ERR_CLOSED",
  "UND_ERR_HEADERS_TIMEOUT", "UND_ERR_BODY_TIMEOUT", "UND_ERR_CONNECT_TIMEOUT",
]);

const sleepFor = (s) => new Promise((r) => setTimeout(r, s * 1000));
const netWait = (attempt) => Math.min(NET_MAX_WAIT, 2 * 2 ** attempt) + Math.random();

function retryAfter(res, attempt) {
  const v = Number.parseFloat(res.headers.get("retry-after"));
  const wait = Number.isFinite(v) ? v : 10.0 * (attempt + 1);
  return Math.max(1, Math.min(MAX_RETRY_WAIT, Math.trunc(wait)));
}

function stillRateLimited(detail, waited) {
  return `${detail} — still rate-limited after ${Math.round(waited)}s of waiting. Too many requests from this address: is another kaeris run going at the same time? Run them one after another, or lower --jobs.`;
}

// What fetch threw, sorted: "refused" (never connected), "dropped" (cut mid-request) or other.
function netKind(e) {
  if (e && (e.name === "TimeoutError" || e.name === "AbortError")) return ["dropped", "TimeoutError"];
  const cause = (e && e.cause) || e || {};
  const code = cause.code || cause.name || "";
  if (code === "ECONNREFUSED") return ["refused", "ConnectionRefusedError"];
  if (DROPPED.has(code)) return ["dropped", code];
  return ["other", cause.message || code || String(e)];
}

async function errMessage(res) {
  let detail;
  try {
    const body = JSON.parse(await res.text());
    detail = (body && (body.detail || body.error)) || JSON.stringify(body);
    if (typeof detail !== "string") detail = JSON.stringify(detail);
  } catch {
    detail = res.statusText || "error";
  }
  return `HTTP ${res.status}: ${detail}`;
}

function connectionLost(apiUrl, path, tries, kind) {
  const job = /\/api\/(?:status|receipt|preview|download)\/([^/?]+)/.exec(path);
  const kept = job ? `The job ${job[1]} is still on the server; nothing is sent twice. ` : "";
  return `Lost the connection to ${apiUrl} (${kind}) after ${tries} tries. ${kept}Run the same command again to continue.`;
}

export class Client {
  constructor({ apiUrl = DEFAULT_API, apiKey = null, openrouterKey = null, timeout = 180 } = {}) {
    this.apiUrl = checkedApiUrl(apiUrl);
    this.apiKey = checkedKey(apiKey, "KAERIS API key");
    this.openrouterKey = checkedKey(openrouterKey, "OpenRouter key");
    this.timeout = timeout;
    this.editTokens = new Map();
    this.jobWarnings = new Map();
    this.pollSlowdown = 1.0;
  }

  headers(extra) {
    const h = { "User-Agent": "kaeris-cli/" + version };
    if (this.apiKey) h["X-API-Key"] = this.apiKey;
    if (this.openrouterKey) h["X-OpenRouter-Key"] = this.openrouterKey;
    return { ...h, ...(extra || {}) };
  }

  // One request, following a redirect only while it stays on the same host and port, and never
  // from https to http: the key travels in our own headers, which fetch would carry anywhere.
  async fetch(path, { method = "GET", body, headers } = {}) {
    let url = this.apiUrl + path;
    for (let hop = 0; ; hop++) {
      const res = await fetch(url, { method, body, headers: this.headers(headers), redirect: "manual", signal: AbortSignal.timeout(this.timeout * 1000) });
      if (![301, 302, 303, 307, 308].includes(res.status) || !res.headers.get("location")) return res;
      if (hop >= MAX_REDIRECTS) throw new KaerisError(`Too many redirects from ${this.apiUrl}`);
      const next = new URL(res.headers.get("location"), url);
      const from = new URL(url);
      const port = (u) => u.port || (u.protocol === "https:" ? "443" : "80");
      if (from.hostname.toLowerCase() !== next.hostname.toLowerCase() || port(from) !== port(next)) {
        throw new KaerisError(`Refusing to follow a redirect from ${from.hostname}:${port(from)} to ${next.hostname}:${port(next)} — your API key would be sent to a different server. Check --api-url.`);
      }
      if (from.protocol === "https:" && next.protocol !== "https:") {
        throw new KaerisError("Refusing to follow a redirect from https to http — your API key would travel unencrypted.");
      }
      if (res.status === 303 || ((res.status === 301 || res.status === 302) && method === "POST")) {
        method = "GET";
        body = undefined;
      }
      url = next.href;
    }
  }

  // A read: a 429 waited out (READ_RETRIES times), a dropped or refused connection asked again.
  async get(path, headers) {
    let waited = 0;
    for (let attempt = 0; ; attempt++) {
      let res;
      try {
        res = await this.fetch(path, { headers });
      } catch (e) {
        if (e instanceof KaerisError) throw e;
        const [kind, name] = netKind(e);
        if (kind === "other") throw new KaerisError(`Cannot reach ${this.apiUrl}: ${name}`);
        if (attempt < NET_RETRIES) {
          await sleepFor(netWait(attempt));
          continue;
        }
        throw new KaerisError(connectionLost(this.apiUrl, path, attempt + 1, name));
      }
      if (res.ok) return Buffer.from(await res.arrayBuffer());
      if (res.status === 429) {
        this.pollSlowdown = Math.min(MAX_POLL_SLOWDOWN, this.pollSlowdown * POLL_SLOWDOWN);
        if (attempt < READ_RETRIES) {
          const wait = retryAfter(res, attempt) + Math.random() * 2;
          await res.arrayBuffer().catch(() => {});
          await sleepFor(wait);
          waited += wait;
          continue;
        }
        throw new KaerisError(stillRateLimited(await errMessage(res), waited), 429);
      }
      throw new KaerisError(await errMessage(res), res.status);
    }
  }

  async getJson(path, headers) {
    const raw = await this.get(path, headers);
    try {
      return JSON.parse(raw.toString("utf8"));
    } catch {
      throw new KaerisError(`${this.apiUrl}${path} did not answer with JSON`);
    }
  }

  languages() {
    return this.getJson("/api/languages");
  }

  config() {
    return this.getJson("/api/config");
  }

  keyInfo() {
    return this.getJson("/api/key/info");
  }

  // POST a file for translation; returns the job id. Optional fields go only when set, so an
  // older server sees the request it knows.
  async submit(filename, content, languages, opts = {}) {
    const form = new FormData();
    form.append("file", new Blob([content], { type: "application/octet-stream" }), filename);
    form.append("languages", languages.join(","));
    if (opts.glossary && opts.glossary.length) form.append("glossary", opts.glossary.join(","));
    if (opts.tone) form.append("tone", opts.tone);
    if (opts.icu) form.append("icu", "true");
    if (opts.translateServiceKeys) form.append("translate_service_keys", "true");
    if (opts.appContext) form.append("app_context", opts.appContext);
    if (opts.model) form.append("model", opts.model);
    if (opts.models && Object.keys(opts.models).length) form.append("models", JSON.stringify(opts.models));
    if (opts.terms && opts.terms.length) form.append("terms", JSON.stringify(opts.terms));
    // Built once: FormData picks its boundary when it is turned into a body.
    const req = new Request("http://x/", { method: "POST", body: form });
    const body = Buffer.from(await req.arrayBuffer());
    const ctype = req.headers.get("content-type");

    let waited = 0;
    let data;
    for (let attempt = 0; ; attempt++) {
      let res;
      try {
        res = await this.fetch("/api/translate", { method: "POST", body, headers: { "Content-Type": ctype } });
      } catch (e) {
        if (e instanceof KaerisError) throw e;
        const [kind, name] = netKind(e);
        if (kind === "refused" && attempt < NET_RETRIES) {
          await sleepFor(netWait(attempt));
          continue;
        }
        if (kind === "dropped") {
          throw new KaerisError(`Lost the connection to ${this.apiUrl} (${name}) while sending the file; it may have reached the server, so it was not sent again. Run the same command again to continue.`);
        }
        throw new KaerisError(`Cannot reach ${this.apiUrl}: ${name}`);
      }
      if (res.status === 429 && attempt < SUBMIT_RETRIES) {
        // The job was never started: nothing is charged twice.
        const wait = retryAfter(res, attempt);
        await res.arrayBuffer().catch(() => {});
        await sleepFor(wait);
        waited += wait;
        continue;
      }
      if (res.status === 429) throw new KaerisError(stillRateLimited(await errMessage(res), waited), 429);
      if (!res.ok) throw new KaerisError(await errMessage(res), res.status);
      try {
        data = JSON.parse(await res.text());
      } catch {
        throw new KaerisError(`${this.apiUrl}/api/translate did not answer with JSON`);
      }
      break;
    }
    const jobId = data && data.job_id;
    if (!jobId) throw new KaerisError(`No job_id in response: ${JSON.stringify(data)}`);
    this.editTokens.set(jobId, data.edit_token || "");
    this.jobWarnings.set(jobId, (data.warnings || []).map(String));
    return jobId;
  }

  // Poll until done or error; returns the final status.
  async poll(jobId, onProgress, interval = 1.0, maxWait = 1800) {
    const deadline = Date.now() + maxWait * 1000;
    while (Date.now() < deadline) {
      const status = await this.getJson(`/api/status/${jobId}`);
      if (onProgress) onProgress(status);
      if (status.status === "done") return status;
      if (status.status === "error") {
        const message = status.error || "Translation failed";
        if (status.retryable || message.includes(RESTART_PHRASE)) throw new KaerisInterrupted(message);
        throw new KaerisError(message);
      }
      await sleepFor(interval * this.pollSlowdown);
    }
    throw new KaerisError(`Still running after ${maxWait}s (job ${jobId}). The translation continues on the server and is not charged twice.`);
  }

  async receipt(jobId) {
    const token = this.editTokens.get(jobId) || "";
    const headers = token ? { "X-Job-Token": token } : undefined;
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.getJson(`/api/receipt/${jobId}`, headers);
      } catch (e) {
        if (!(e instanceof KaerisError) || e.code !== 409 || attempt === RECEIPT_RETRIES) throw e;
        await sleepFor(1);
      }
    }
  }

  preview(jobId) {
    return this.getJson(`/api/preview/${jobId}`);
  }

  // The result archive as [[name, bytes]]. Every name is checked before anything is returned:
  // an archive with one bad name is not ours, and nothing from it is written.
  async download(jobId) {
    const raw = await this.get(`/api/download/${jobId}`);
    let members;
    try {
      members = readZip(raw);
    } catch (e) {
      if (e instanceof BadZip) throw new KaerisError(`The result archive cannot be read: ${e.message}`);
      throw e;
    }
    const out = [];
    for (const { name, data } of members) {
      if (name.endsWith("/") || name.endsWith("\\")) continue;
      out.push([safeMemberName(name), data]);
    }
    return out;
  }
}

// A random id for temporary files.
export const tmpSuffix = () => crypto.randomBytes(6).toString("hex");
