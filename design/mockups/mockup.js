// Mockup runtime: device/theme switch, inline icons, the brand mark and a small notation renderer
// (Bravura glyphs, SMuFL code points). Static mockups only; the apps render notation with Verovio/alphaTab.
(function () {
  const params = new URLSearchParams(location.search);
  document.documentElement.dataset.device = params.get("device") || "phone";
  if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");

  const MARK = "M9.5 10a4.5 4.5 0 0 1 9 0V31C29.5 31 41.5 26 50.5 15C52 13.5 54.5 14 54.5 16V26C54.5 45 39.5 58 18.5 59H9.5Z M18.5 41V51C31.5 49.5 40.5 42 44.5 31C37.5 37 28.5 40.5 18.5 41Z";
  window.markSVG = (size, cls = "") =>
    `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="${MARK}"/></svg>`;

  // Bandroom's menu-bar / tray icon: the mark plus a state badge that differs by shape (never colour alone).
  // The badge is knocked out of the mark so it reads at 16 px. kind: running | busy | attention | stopped |
  // starting | updating | error | setup. `pie` is the busy fraction, drawn in 8 steps.
  let maskId = 0;
  window.stateMarkSVG = (kind, size, pie = 0.62) => {
    const id = `sm${maskId++}`;
    const cut = kind === "running" ? "" : `<circle cx="50" cy="50" r="17" fill="black"/>`;
    const b = {
      running: "",
      busy: (() => {
        const f = Math.round(pie * 8) / 8, a = f * 2 * Math.PI, r = 11;
        const x = 50 + r * Math.sin(a), y = 50 - r * Math.cos(a);
        return `<circle cx="50" cy="50" r="12" fill="none" stroke="currentColor" stroke-width="3"/>` +
          `<path fill="currentColor" d="M50 50V${50 - r}A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}Z"/>`;
      })(),
      attention: `<path fill="currentColor" d="M50 35.5 64 61H36Z"/>`,
      stopped: `<rect x="39" y="39" width="22" height="22" rx="3" fill="currentColor"/>`,
      starting: `<circle cx="38.5" cy="50" r="4.5" fill="currentColor"/><circle cx="50" cy="50" r="4.5" fill="currentColor"/><circle cx="61.5" cy="50" r="4.5" fill="currentColor"/>`,
      updating: `<path fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" d="M60 45a11 11 0 1 0 1 8"/><path fill="currentColor" d="M63.5 36v12h-12Z"/>`,
      error: `<circle cx="50" cy="50" r="13" fill="currentColor"/><path stroke="var(--sm-knock, var(--bc-surface-raised))" stroke-width="4" stroke-linecap="round" d="m44.5 44.5 11 11m0-11-11 11"/>`,
      setup: `<path fill="none" stroke="currentColor" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" d="M50 37v24m-9-9 9 9 9-9"/>`,
    }[kind];
    return `<svg width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true"><defs><mask id="${id}"><rect width="64" height="64" fill="white"/>${cut}</mask></defs>` +
      `<path fill="currentColor" fill-rule="evenodd" mask="url(#${id})" d="${MARK}"/>${b}</svg>`;
  };

  function icons() {
    document.querySelectorAll("[data-state-mark]").forEach((el) => {
      el.outerHTML = window.stateMarkSVG(el.dataset.stateMark, +el.dataset.size || 18, +(el.dataset.pie || 0.62));
    });
    document.querySelectorAll("i[data-i]").forEach((el) => {
      const d = (globalThis.BrasscribeIcons || {})[el.dataset.i];
      if (!d) { el.textContent = "?"; return; }
      const cls = "i " + (el.className || "");
      el.outerHTML = `<svg class="${cls}" viewBox="0 -960 960 960" aria-hidden="true"><path d="${d}"/></svg>`;
    });
    document.querySelectorAll("[data-mark]").forEach((el) => {
      el.outerHTML = window.markSVG(+el.dataset.mark || 24, el.className);
    });
  }

  // ---------------------------------------------------------------- notation
  const G = { gClef: "", sharp: "", flat: "", natural: "", black: "", half: "", whole: "",
    flagUp: "", flagDown: "", rq: "", r8: "", rh: "", rw: "" };
  const BEATS = { w: 4, h: 2, q: 1, e: 0.5 };
  const SHARPS = [8, 5, 9, 6, 3, 7, 4];
  const FLATS = [4, 7, 3, 6, 2, 5, 1];
  const digit = (n) => String.fromCharCode(0xE080 + n);

  // spec: { sp, width, key, time:[4,4], clef:true, barNumbers:true,
  //         bars:[{n, adlib}], staves:[{name, bars:[[events]]}], cursor:{bar, frac}, loop:{from,to}, focus:{staff,bar,ev},
  //         selection:{from,to} }
  // event: {s: staff step (0 = bottom line), d: 'q'|'e'|'h'|'w', u: 0|1|2, acc: '#'|'b'|'n', beam: 'start'|'end'} or {r:'q'|'e'|'h'|'w'}
  function drawSystem(spec) {
    const sp = spec.sp || 8;
    const fs = sp * 4;
    const nameW = spec.names === false ? 0 : (spec.nameWidth || sp * 9);
    const staffGap = spec.staffGap || sp * 9;
    const top = spec.top || sp * 6;
    const W = spec.width;
    const staves = spec.staves;
    const H = top + staves.length * 4 * sp + (staves.length - 1) * staffGap + sp * 5;
    const x0 = nameW;
    const key = spec.key || 0;
    const prefix = (spec.clef === false ? 0 : sp * 3.2) + Math.abs(key) * sp * 1.05 + (spec.time ? sp * 2.4 : 0) + sp * 0.8;
    const barsX = x0 + prefix;
    const nb = spec.bars.length;
    const barW = (W - barsX - sp) / nb;
    const staffTop = (i) => top + i * (4 * sp + staffGap);
    const y = (i, s) => staffTop(i) + 4 * sp - (s * sp) / 2;
    const sysTop = staffTop(0) - sp * 1.5;
    const sysBot = staffTop(staves.length - 1) + 4 * sp + sp * 1.5;
    const out = [];
    const bx = (b) => barsX + b * barW;

    // Bands behind the notes: ad lib, selection, loop (never stacked: loop wins), cursor bar.
    spec.bars.forEach((bar, b) => {
      const inLoop = spec.loop && b >= spec.loop.from && b <= spec.loop.to;
      if (bar.adlib && !inLoop) out.push(`<rect class="adlib-tint" x="${bx(b)}" y="${sysTop}" width="${barW}" height="${sysBot - sysTop}"/>`);
    });
    if (spec.selection) {
      const a = bx(spec.selection.from), z = bx(spec.selection.to + 1);
      out.push(`<rect class="cursor-tint" style="fill:var(--bc-selection-tint)" x="${a}" y="${sysTop}" width="${z - a}" height="${sysBot - sysTop}"/>`);
      out.push(`<rect x="${a + 0.5}" y="${sysTop + 0.5}" width="${z - a - 1}" height="${sysBot - sysTop - 1}" fill="none" style="stroke:var(--bc-selection-edge)"/>`);
    }
    if (spec.loop) {
      const a = bx(spec.loop.from), z = bx(spec.loop.to + 1);
      out.push(`<rect class="loop-tint" x="${a}" y="${sysTop}" width="${z - a}" height="${sysBot - sysTop}"/>`);
    }
    if (spec.cursor && !(spec.loop && spec.cursor.bar >= spec.loop.from && spec.cursor.bar <= spec.loop.to)) {
      const b = spec.cursor.bar;
      out.push(`<rect class="cursor-tint" x="${bx(b)}" y="${sysTop}" width="${barW}" height="${sysBot - sysTop}"/>`);
    }

    staves.forEach((st, i) => {
      const t = staffTop(i);
      for (let l = 0; l < 5; l++) out.push(`<line class="staffline" x1="${x0}" x2="${W - sp}" y1="${t + l * sp}" y2="${t + l * sp}" stroke-width="${Math.max(1, sp * 0.13)}"/>`);
      if (nameW) out.push(`<text class="partname" x="${nameW - sp * 1.2}" y="${t + 2.4 * sp}" text-anchor="end" font-size="${Math.max(12, sp * 1.55)}">${st.name}</text>`);
      let cx = x0 + sp * 0.6;
      if (spec.clef !== false) { out.push(`<text class="ink" font-family="Bravura" font-size="${fs}" x="${cx}" y="${y(i, 2)}">${G.gClef}</text>`); cx += sp * 3.2; }
      const ks = key > 0 ? SHARPS : FLATS;
      for (let k = 0; k < Math.abs(key); k++) { out.push(`<text class="ink" font-family="Bravura" font-size="${fs}" x="${cx}" y="${y(i, ks[k])}">${key > 0 ? G.sharp : G.flat}</text>`); cx += sp * 1.05; }
      if (spec.time) {
        out.push(`<text class="ink" font-family="Bravura" font-size="${fs}" x="${cx + sp * 0.2}" y="${y(i, 6)}">${digit(spec.time[0])}</text>`);
        out.push(`<text class="ink" font-family="Bravura" font-size="${fs}" x="${cx + sp * 0.2}" y="${y(i, 2)}">${digit(spec.time[1])}</text>`);
      }
      // bar lines
      spec.bars.forEach((bar, b) => {
        const xe = bx(b + 1);
        const dashed = bar.adlib ? `stroke-dasharray="${sp * 0.5} ${sp * 0.4}"` : "";
        out.push(`<line class="staffline" x1="${xe}" x2="${xe}" y1="${t}" y2="${t + 4 * sp}" stroke-width="${Math.max(1.2, sp * 0.16)}" ${dashed}/>`);
      });
      // notes
      (st.bars || []).forEach((events, b) => {
        let beat = 0;
        const inner = barW - sp * (b === 0 ? 3.0 : 2.2);
        const start = bx(b) + sp * (b === 0 ? 2.2 : 1.4);
        const beam = [];
        (events || []).forEach((e, k) => {
          const x = start + (beat / (spec.time ? spec.time[0] : 4)) * inner;
          beat += BEATS[e.d || e.r];
          if (e.r) {
            const glyph = { q: G.rq, e: G.r8, h: G.rh, w: G.rw }[e.r];
            const ry = e.r === "w" ? y(i, 6) : y(i, 4);
            out.push(`<text class="ink" font-family="Bravura" font-size="${fs}" x="${x}" y="${ry}">${glyph}</text>`);
            return;
          }
          const cls = e.u === 1 ? "u" : e.u === 2 ? "vu" : "ink";
          const ny = y(i, e.s);
          // ledger lines
          const led = [];
          for (let s = -2; s >= e.s; s -= 2) led.push(s);
          for (let s = 10; s <= e.s; s += 2) led.push(s);
          led.forEach((s) => out.push(`<line class="staffline" x1="${x - sp * 0.4}" x2="${x + sp * 1.58}" y1="${y(i, s)}" y2="${y(i, s)}" stroke-width="${Math.max(1, sp * 0.16)}"/>`));
          if (e.acc) out.push(`<text class="${cls}" font-family="Bravura" font-size="${fs}" x="${x - sp * 1.15}" y="${ny}">${{ "#": G.sharp, b: G.flat, n: G.natural }[e.acc]}</text>`);
          const head = e.d === "h" ? G.half : e.d === "w" ? G.whole : G.black;
          out.push(`<text class="${cls}" font-family="Bravura" font-size="${fs}" x="${x}" y="${ny}">${head}</text>`);
          const up = e.s < 4;
          const note = { x, ny, up, cls, e };
          if (e.d !== "w") {
            if (e.beam) beam.push(note);
            else drawStem(out, note, sp, fs, e.d === "e");
          }
          if (e.beam === "end" && beam.length) { drawBeam(out, beam.splice(0), sp); }
          // uncertainty mark: "?" above the staff (or above a high note), boxed below 0.4
          if (e.u) {
            const qy = Math.min(t - sp * 1.4, ny - sp * (up ? 4.8 : 2.4));
            const qs = sp * 1.7;
            const qx = x + sp * 0.59;
            if (e.u === 2) out.push(`<rect class="qbox" x="${qx - qs * 0.42}" y="${qy - qs * 0.86}" width="${qs * 0.84}" height="${qs * 1.06}" rx="${sp * 0.15}" stroke-width="${Math.max(1.2, sp * 0.15)}"/>`);
            out.push(`<text class="qmark ${cls}" font-size="${qs}" x="${qx}" y="${qy}" text-anchor="middle">?</text>`);
          }
          if (spec.focus && spec.focus.staff === i && spec.focus.bar === b && spec.focus.ev === k) {
            const g = spec.focusGap || 3;
            out.push(`<rect class="focus" x="${x - g - sp * 0.2}" y="${ny - sp * 0.7 - g}" width="${sp * 1.58 + 2 * g}" height="${sp * 1.4 + 2 * g}" rx="3" stroke-width="2"/>`);
          }
        });
      });
    });

    // front layer: bar numbers, loop edges, ad lib text, cursor line
    if (spec.barNumbers !== false) {
      spec.bars.forEach((bar, b) => {
        if (b === 0) out.push(`<text class="barnum" x="${x0 + sp * 0.4}" y="${staffTop(0) - sp * 3.2}" font-size="${Math.max(11, sp * 1.35)}">${bar.n}</text>`);
        else if (spec.barNumbers === "all") out.push(`<text class="barnum" x="${bx(b)}" y="${staffTop(0) - sp * 3.2}" text-anchor="middle" font-size="${Math.max(11, sp * 1.35)}">${bar.n}</text>`);
      });
    }
    spec.bars.forEach((bar, b) => {
      if (bar.adlib && (b === 0 || !spec.bars[b - 1].adlib)) {
        out.push(`<text class="adlib-text" x="${bx(b) + sp * 0.6}" y="${sysTop - sp * 0.6}" font-size="${sp * 2}">ad lib.</text>`);
      }
      if (!bar.adlib && b > 0 && spec.bars[b - 1].adlib) {
        out.push(`<text class="adlib-text" x="${bx(b) + sp * 0.6}" y="${sysTop - sp * 0.6}" font-size="${sp * 2}">a tempo</text>`);
      }
    });
    if (spec.loop) {
      const a = bx(spec.loop.from), z = bx(spec.loop.to + 1);
      const w = 3, tick = sp * 0.9;
      out.push(`<path class="loop-edge" d="M${a} ${sysTop}h${tick}v${w}h${-tick + w}v${sysBot - sysTop - 2 * w}h${tick - w}v${w}h${-tick}Z"/>`);
      out.push(`<path class="loop-edge" d="M${z} ${sysTop}h${-tick}v${w}h${tick - w}v${sysBot - sysTop - 2 * w}h${-tick + w}v${w}h${tick}Z"/>`);
      out.push(`<text class="loop-label" x="${a + tick + 4}" y="${sysTop - 6}" font-size="${Math.max(12, sp * 1.45)}">${spec.loop.label || "Loop"}</text>`);
    }
    if (spec.cursor) {
      const cx = bx(spec.cursor.bar) + sp * 1.4 + (barW - sp * 2.2) * (spec.cursor.frac || 0) - 1.5;
      out.push(`<rect class="cursor" x="${cx}" y="${sysTop}" width="3" height="${sysBot - sysTop}" rx="1.5"/>`);
    }
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${spec.label || "Score"}">${out.join("")}</svg>`;
  }

  function stemPos(n, sp) {
    return n.up ? { x: n.x + sp * 1.18 - sp * 0.06, y1: n.ny - sp * 0.17, y2: n.ny - sp * 3.5 }
      : { x: n.x + sp * 0.06, y1: n.ny + sp * 0.17, y2: n.ny + sp * 3.5 };
  }
  function drawStem(out, n, sp, fs, flag) {
    const p = stemPos(n, sp);
    out.push(`<line class="stem" x1="${p.x}" x2="${p.x}" y1="${p.y1}" y2="${p.y2}" stroke-width="${sp * 0.12}" style="stroke:var(--bc-${n.cls === "ink" ? "ink" : n.cls === "u" ? "uncertain" : "very-uncertain"})"/>`);
    if (flag) out.push(`<text class="${n.cls}" font-family="Bravura" font-size="${fs}" x="${p.x - sp * 0.06}" y="${p.y2}">${n.up ? G.flagUp : G.flagDown}</text>`);
  }
  function drawBeam(out, notes, sp) {
    const up = notes.filter((n) => n.up).length >= notes.length / 2;
    notes.forEach((n) => (n.up = up));
    const ps = notes.map((n) => stemPos(n, sp));
    const y1 = up ? Math.min(...ps.map((p) => p.y2)) : Math.max(...ps.map((p) => p.y2));
    const a = ps[0], z = ps[ps.length - 1];
    const slope = Math.max(-0.12, Math.min(0.12, ((notes[notes.length - 1].ny - notes[0].ny) / (z.x - a.x)) * 0.35));
    const by = (x) => y1 + (x - a.x) * slope;
    notes.forEach((n, k) => {
      const p = ps[k];
      const c = n.cls === "u" ? "uncertain" : n.cls === "vu" ? "very-uncertain" : "ink";
      out.push(`<line x1="${p.x}" x2="${p.x}" y1="${p.y1}" y2="${by(p.x)}" stroke-width="${sp * 0.12}" style="stroke:var(--bc-${c})"/>`);
    });
    const th = sp * 0.5 * (up ? 1 : -1);
    out.push(`<path class="ink" d="M${a.x - sp * 0.06} ${by(a.x)}L${z.x + sp * 0.06} ${by(z.x)}l0 ${th}L${a.x - sp * 0.06} ${by(a.x) + th}Z"/>`);
  }

  window.drawSystem = drawSystem;
  window.addEventListener("DOMContentLoaded", async () => {
    await Promise.all([
      document.fonts.load("32px Bravura", "\uE0A4\uE050"),
      document.fonts.load("40px 'Instrument Serif'", "Brasscribe"),
      document.fonts.load("italic 40px 'Instrument Serif'", "Play"),
    ]).catch(() => {});
    if (params.get("lang") === "nb") {
      document.documentElement.lang = "nb";
      document.querySelectorAll("[data-nb]").forEach((el) => { el.textContent = el.dataset.nb; });
    }
    document.querySelectorAll("[data-score]").forEach((el) => {
      const spec = window.SCORES[el.dataset.score];
      el.classList.add("score");
      el.innerHTML = drawSystem({ ...spec, width: el.clientWidth || spec.width, ...(el.dataset.sp ? { sp: +el.dataset.sp } : {}) });
    });
    icons();
    document.body.dataset.ready = "1";
  });
})();
