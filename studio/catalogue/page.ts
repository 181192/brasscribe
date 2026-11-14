// A picture of a page, made here so that no picture is kept in git: a white sheet with one empty staff, as a
// PNG. It is what the catalogue's engine answers for the input of a run that read a page, and what the new-run
// form is given as its pages.
import { crc32, deflateSync } from "node:zlib";

function chunk(type: string, data: Buffer): Buffer {
  const body = Buffer.concat([Buffer.from(type, "latin1"), data]);
  const out = Buffer.alloc(body.length + 8);
  out.writeUInt32BE(data.length, 0);
  body.copy(out, 4);
  out.writeUInt32BE(crc32(body), body.length + 4);
  return out;
}

/** An 8-bit greyscale PNG, `width` by `height`: white, with five staff lines across it. */
export function pagePng(width = 480, height = 200): Buffer {
  const rows = Buffer.alloc((width + 1) * height, 0xff);
  for (let y = 0; y < height; y++) {
    rows[y * (width + 1)] = 0; // the row's filter: none
    const line = y >= 60 && y <= 140 && (y - 60) % 20 < 2;
    if (line) rows.fill(0x20, y * (width + 1) + 1 + 24, (y + 1) * (width + 1) - 24);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.set([8, 0, 0, 0, 0], 8); // 8 bits, greyscale, deflate, no filter set of its own, not interlaced
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}
