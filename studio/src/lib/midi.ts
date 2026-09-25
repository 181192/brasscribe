// Standard MIDI File reader: notes with times in seconds (tempo map applied).

export interface MidiNote {
  pitch: number;
  velocity: number;
  channel: number;
  track: number;
  start: number; // seconds
  end: number; // seconds
}

export interface MidiFile {
  format: number;
  ticksPerQuarter: number;
  notes: MidiNote[];
  tempos: { tick: number; usPerQuarter: number }[];
}

class Reader {
  pos = 0;
  constructor(private readonly d: DataView) {}
  get length(): number {
    return this.d.byteLength;
  }
  u8(): number {
    return this.d.getUint8(this.pos++);
  }
  u16(): number {
    const v = this.d.getUint16(this.pos);
    this.pos += 2;
    return v;
  }
  u32(): number {
    const v = this.d.getUint32(this.pos);
    this.pos += 4;
    return v;
  }
  str(n: number): string {
    let s = "";
    for (let i = 0; i < n; i++) s += String.fromCharCode(this.u8());
    return s;
  }
  vlq(): number {
    let v = 0;
    for (let i = 0; i < 4; i++) {
      const b = this.u8();
      v = (v << 7) | (b & 0x7f);
      if (!(b & 0x80)) break;
    }
    return v;
  }
}

interface RawNote {
  pitch: number;
  velocity: number;
  channel: number;
  track: number;
  on: number;
  off: number;
}

export function parseMidi(buf: ArrayBuffer): MidiFile {
  const r = new Reader(new DataView(buf));
  if (r.str(4) !== "MThd") throw new Error("not a MIDI file");
  const hlen = r.u32();
  const format = r.u16();
  const ntracks = r.u16();
  const division = r.u16();
  r.pos = 8 + hlen;
  if (division & 0x8000) throw new Error("SMPTE time division is not supported");
  const tempos: { tick: number; usPerQuarter: number }[] = [];
  const raw: RawNote[] = [];

  for (let t = 0; t < ntracks && r.pos < r.length; t++) {
    const id = r.str(4);
    const len = r.u32();
    const end = r.pos + len;
    if (id !== "MTrk") {
      r.pos = end;
      continue;
    }
    let tick = 0;
    let status = 0;
    const open = new Map<number, RawNote[]>();
    while (r.pos < end) {
      tick += r.vlq();
      let b = r.u8();
      if (b === 0xff) {
        const type = r.u8();
        const n = r.vlq();
        if (type === 0x51 && n === 3) {
          tempos.push({ tick, usPerQuarter: (r.u8() << 16) | (r.u8() << 8) | r.u8() });
        } else r.pos += n;
        continue;
      }
      if (b === 0xf0 || b === 0xf7) {
        r.pos += r.vlq();
        continue;
      }
      let d1: number;
      if (b & 0x80) {
        status = b;
        d1 = r.u8();
      } else {
        d1 = b; // running status
        b = status;
      }
      const kind = status & 0xf0;
      const ch = status & 0x0f;
      if (kind === 0xc0 || kind === 0xd0) continue;
      const d2 = r.u8();
      const key = ch * 128 + d1;
      if (kind === 0x90 && d2 > 0) {
        const note = { pitch: d1, velocity: d2, channel: ch, track: t, on: tick, off: -1 };
        const list = open.get(key) ?? [];
        list.push(note);
        open.set(key, list);
        raw.push(note);
      } else if (kind === 0x80 || (kind === 0x90 && d2 === 0)) {
        const list = open.get(key);
        const note = list?.shift();
        if (note) note.off = tick;
      }
    }
    for (const list of open.values()) for (const n of list) n.off = tick;
    r.pos = end;
  }

  tempos.sort((a, b) => a.tick - b.tick);
  const seconds = tickToSeconds(tempos, division);
  const notes = raw
    .map((n) => ({
      pitch: n.pitch,
      velocity: n.velocity,
      channel: n.channel,
      track: n.track,
      start: seconds(n.on),
      end: seconds(Math.max(n.off, n.on)),
    }))
    .sort((a, b) => a.start - b.start || a.pitch - b.pitch);
  return { format, ticksPerQuarter: division, notes, tempos };
}

export function tickToSeconds(tempos: { tick: number; usPerQuarter: number }[], tpq: number): (tick: number) => number {
  const map = [{ tick: 0, us: 500000, at: 0 }];
  for (const t of tempos) {
    const last = map[map.length - 1];
    const at = last.at + ((t.tick - last.tick) * last.us) / tpq / 1e6;
    if (t.tick === last.tick) {
      last.us = t.usPerQuarter;
    } else map.push({ tick: t.tick, us: t.usPerQuarter, at });
  }
  return (tick: number) => {
    let seg = map[0];
    for (const m of map) {
      if (m.tick <= tick) seg = m;
      else break;
    }
    return seg.at + ((tick - seg.tick) * seg.us) / tpq / 1e6;
  };
}
