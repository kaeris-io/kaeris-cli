// Reads the result archive the API sends (Python's zipfile does this in the original). Stored and
// deflated members only, which is all zipfile writes; no ZIP64, no encryption. Read from the
// central directory, as zipfile does, and each member's CRC-32 is checked.
import zlib from "node:zlib";

export class BadZip extends Error {}

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function endRecord(buf) {
  // The end-of-central-directory record is the last 22 bytes plus a comment of up to 65,535.
  const stop = Math.max(0, buf.length - 22 - 0xffff);
  for (let i = buf.length - 22; i >= stop; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) return i;
  }
  throw new BadZip("File is not a zip file");
}

// [{name, data}] in archive order. Names are as the archive spells them: the caller checks them.
export function readZip(buf) {
  if (!Buffer.isBuffer(buf)) buf = Buffer.from(buf);
  const end = endRecord(buf);
  const count = buf.readUInt16LE(end + 10);
  let p = buf.readUInt32LE(end + 16);
  const out = [];
  for (let i = 0; i < count; i++) {
    if (p + 46 > buf.length || buf.readUInt32LE(p) !== 0x02014b50) throw new BadZip("Bad central directory in the result archive");
    const flags = buf.readUInt16LE(p + 8);
    const method = buf.readUInt16LE(p + 10);
    const crc = buf.readUInt32LE(p + 16);
    const packedSize = buf.readUInt32LE(p + 20);
    const size = buf.readUInt32LE(p + 24);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const rawName = buf.subarray(p + 46, p + 46 + nameLen);
    const name = flags & 0x800 ? rawName.toString("utf8") : rawName.toString("latin1");
    p += 46 + nameLen + extraLen + commentLen;
    if (flags & 1) throw new BadZip(`${name}: encrypted members are not read`);
    if (local + 30 > buf.length || buf.readUInt32LE(local) !== 0x04034b50) throw new BadZip(`${name}: bad local header in the result archive`);
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const packed = buf.subarray(start, start + packedSize);
    if (packed.length !== packedSize) throw new BadZip(`${name}: the result archive is cut short`);
    let data;
    if (method === 0) data = Buffer.from(packed);
    else if (method === 8) data = zlib.inflateRawSync(packed);
    else throw new BadZip(`${name}: compression method ${method} is not read`);
    if (data.length !== size || crc32(data) !== crc) throw new BadZip(`Bad CRC-32 for file '${name}'`);
    out.push({ name, data });
  }
  return out;
}
