// The tab page's side of TabPage.swift. The app tells it the song and its colours (show), where the cursor stands
// (cursorAt) and how the screen looks (palette); it answers with the engraving: the page's height, its lines, where
// each bar is and where each mark the app asked for goes, in CSS pixels, so the app can place its own controls (the
// "?" and the boxed "!") over the page and read out the bars.
'use strict';
(function () {
  const at = alphaTab;
  const post = (m) => window.webkit.messageHandlers.tab.postMessage(m);
  const el = document.getElementById('tab');
  const cursor = document.getElementById('cursor');
  const beatWash = document.getElementById('beat');
  let api = null;
  let score = null;
  let palette = null;
  let beats = new Map(); // bar index -> [{tick, x, w}] in time order
  let barBoxes = new Map(); // bar index -> {x, y, w, h}
  let marks = []; // what the app marks: [{staff, bar, tick, notes: [{string, fret, pitchClass, doubt}]}]
  let markStaff = 0; // the staff the marks and the cursor stand on
  let attribution = null; // {x, y, w, h}: where alphaTab's own "alphaTab.net" mark can be; nothing of ours is drawn over it
  let placed = []; // [{mark: index into marks, beat, doubtful: [Note]}]
  const MARK_SPACE = ' '; // the blank text of a marked beat: alphaTab keeps a band above the staff for it
  const MARK_LINE_SPACES = 1.4; // a mark's height in tab line spaces
  // The height of the blank text that keeps the band for a mark. A little more than the mark: alphaTab 1.9 rests its own
  // "alphaTab.net" mark above that text. How tall alphaTab takes a line of text to be depends on the font it finds, so the
  // page measures where the mark was drawn and, while a mark of the app's stands under it, makes the text taller and
  // engraves again (publish).
  const MARK_TEXT_SPACES = 1.6;
  const MARK_TEXT_STEP = 0.4; // what the text grows by while a mark is still under alphaTab's own
  const MARK_TEXT_MAX = 4.4;
  let markText = MARK_TEXT_SPACES;

  window.onerror = (msg, src, line) => post({ kind: 'error', message: String(msg) + ' (' + src + ':' + line + ')' });

  function hidden() {
    const e = at.NotationElement;
    return [e.ScoreTitle, e.ScoreSubTitle, e.ScoreArtist, e.ScoreAlbum, e.ScoreWords, e.ScoreMusic,
      e.ScoreWordsAndMusic, e.ScoreCopyright, e.TrackNames, e.GuitarTuning, e.EffectTempo];
  }

  // The blank text of a marked beat, at the height markText says (in tab line spaces).
  function markFont(s) {
    const r = s.display.resources;
    const text = r.elementFonts.get(at.NotationElement.EffectText);
    if (!text) return;
    const family = text.families ? text.families[0] : text.family;
    r.elementFonts.set(at.NotationElement.EffectText, new at.model.Font(family, markText * lineSpacing(s), text.style, text.weight));
  }

  function settings(opts) {
    const s = new at.Settings();
    s.core.useWorkers = false;
    s.core.enableLazyLoading = false;
    s.core.includeNoteBounds = true;
    s.core.engine = 'svg';
    s.core.fontDirectory = 'alphatab/font/';
    s.core.smuflFontSources = new Map([[at.FontFileFormat.Woff2, 'alphatab/font/Bravura.woff2']]);
    s.display.layoutMode = at.LayoutMode.Page;
    s.display.scale = opts.scale || 1;
    s.display.stretchForce = 0.6;
    s.display.lastSystemFillThreshold = 1;
    s.player.playerMode = at.PlayerMode.Disabled;
    s.player.enableCursor = false;
    s.player.enableSeekToClick = false;
    s.player.enablePlaybackRangeSelection = false;
    s.player.resetPlaybackRangeOnClick = false;
    s.player.scrollMode = at.ScrollMode.Off;
    s.notation.rhythmMode = at.TabRhythmMode.ShowWithBars;
    for (const e of hidden()) s.notation.elements.set(e, false);
    const r = s.display.resources;
    // A marked beat gets blank text, and alphaTab keeps a band above the staff for a line's text: with the text as tall
    // as a mark, the band is the room the marks need, on the lines that have marks and on no others. The band is lifted
    // by a bar number, so a mark stands above the bar's number.
    try {
      markFont(s);
      s.display.effectBandPaddingBottom = s.display.effectBandPaddingBottom + r.barNumberFont.size;
    } catch (e) { /* an alphaTab without these keeps its own band */ }
    applyPalette(s, opts.palette);
    return s;
  }

  // One tab line space in alphaTab's units, unscaled.
  function lineSpacing(s) {
    const e = s.display.resources.engravingSettings;
    return (e && e.tabLineSpacing > 0) ? e.tabLineSpacing : 10;
  }

  function color(hex) { return at.model.Color.fromJson(hex); }

  function applyPalette(s, p) {
    palette = p;
    const r = s.display.resources;
    r.mainGlyphColor = color(p.ink);
    r.secondaryGlyphColor = color(p.ink);
    r.scoreInfoColor = color(p.ink);
    r.staffLineColor = color(p.string);
    r.barSeparatorColor = color(p.string);
    r.barNumberColor = color(p.string);
    cursor.style.background = p.cursor;
    beatWash.style.background = p.cursorTint || 'transparent';
  }

  function tint() {
    if (!score) return;
    const doubt = color(palette.uncertain);
    const subs = [at.model.NoteSubElement.GuitarTabFretNumber, at.model.NoteSubElement.StandardNotationNoteHead];
    for (const t of score.tracks) for (const st of t.staves) for (const b of st.bars) for (const v of b.voices)
      for (const beat of v.beats) for (const n of beat.notes) {
        n.style = null;
        if (doubtful.has(beat.voice.bar.index + ':' + n.string + ':' + n.fret + ':' + beat.playbackStart) || marked.has(n)) {
          const style = new at.model.NoteStyle();
          for (const e of subs) style.colors.set(e, doubt);
          n.style = style;
        }
      }
  }

  let doubtful = new Set();
  let marked = new Set(); // the notes of the placed marks that are in doubt

  // The note of alphaTab's model that a marked note is: by string (counted from the top line, as the app counts) and
  // fret on a tab staff, else by its pitch class.
  function matches(n, m, strings) {
    if (m.string != null && m.fret != null && n.isStringed) return n.fret === m.fret && strings - n.string + 1 === m.string;
    return m.pitchClass == null || ((n.realValue % 12) + 12) % 12 === m.pitchClass;
  }

  // Finds each mark's beat in the score: the same staff and bar, and the same start. Of the beats that start there, in
  // any voice, the one with most of the mark's doubtful notes is its beat. It gets blank text, for the band.
  function place() {
    placed = []; marked = new Set();
    const staves = score.tracks[0].staves;
    marks.forEach((m, i) => {
      const staff = staves[m.staff];
      const bar = staff && staff.bars[m.bar];
      if (!bar) return;
      const strings = staff.tuning ? staff.tuning.length : 0;
      const wanted = m.notes.filter((n) => n.doubt);
      let beat = null, hits = [];
      for (const v of bar.voices) for (const b of v.beats) {
        if (b.isEmpty || Math.abs(b.playbackStart - m.tick) >= 1) continue;
        const found = [];
        for (const w of wanted) { const n = b.notes.find((x) => matches(x, w, strings) && !found.includes(x)); if (n) found.push(n); }
        if (!beat || found.length > hits.length) { beat = b; hits = found; }
      }
      if (!beat) return;
      if (!beat.text || !beat.text.trim()) beat.text = MARK_SPACE;
      for (const n of hits) marked.add(n);
      placed.push({ mark: i, beat });
    });
  }

  // alphaTab reads the second staff of a pair into its fifth voice (MusicXML numbers a second staff's voices from 5)
  // and leaves the first four empty; it draws a rest for an empty first voice, over the numbers. The voice with the
  // bar's music is made the first of its bar.
  function musicInTheFirstVoice() {
    for (const t of score.tracks) for (const st of t.staves) for (const b of st.bars) {
      const v = b.voices;
      if (v.length < 2 || !v[0].isEmpty) continue;
      const k = v.findIndex((x, i) => i > 0 && !x.isEmpty);
      if (k < 0) continue;
      const empty = v[0], music = v[k];
      v[0] = music; v[k] = empty;
      music.index = 0; empty.index = k;
    }
  }

  // Where each placed mark goes in this engraving, in the page's pixels: above its column's numerals and above the
  // bar's number over the staff. x is the middle of the column; columnBottom is how far down its numerals go.
  function markBoxes(lookup) {
    const scale = api.settings.display.scale || 1;
    const ls = lineSpacing(api.settings) * scale;
    const height = MARK_LINE_SPACES * ls;
    const barNumber = api.settings.display.resources.barNumberFont.size * scale;
    const out = [];
    for (const p of placed) {
      const all = lookup.findBeats(p.beat);
      if (!all || all.length === 0) continue;
      const bb = all[0];
      const staff = bb.barBounds.visualBounds;
      let top = Math.min(staff.y, bb.visualBounds.y);
      let columnBottom = staff.y + staff.h;
      let centre = bb.onNotesX > 0 ? bb.onNotesX : bb.visualBounds.x + bb.visualBounds.w / 2;
      let wide = 0;
      if (bb.notes) bb.notes.forEach((n, j) => {
        const h = n.noteHeadBounds;
        top = Math.min(top, h.y);
        columnBottom = Math.max(columnBottom, h.y + h.h);
        if (j === 0) centre = h.x + h.w / 2;
        wide = Math.max(wide, h.w);
      });
      const bottom = Math.min(top - 0.45 * ls, staff.y - barNumber - 0.3 * ls);
      out.push({ mark: p.mark, x: centre, top: bottom - height, bottom, columnBottom, w: Math.max(height, wide + 0.4 * ls) });
    }
    return out;
  }

  // alphaTab 1.9 draws "♪ alphaTab.net" in a score of more than 10 bars, and asks that it stays visible: right-aligned to the
  // last bar of the first system, above everything alphaTab placed over the top staff (the app's marks are in that band as
  // blank text, so it rests above them). It is at a height alphaTab does not report, so the zone is the band above the staff.
  function attributionZone(lookup) {
    if (score.masterBars.length <= 10 && api.tracks.length <= 2) return null;
    const sys = lookup.staffSystems[0];
    if (!sys || sys.bars.length === 0) return null;
    const last = sys.bars[sys.bars.length - 1];
    const top = sys.visualBounds.y;
    const staffTop = last.bars.length > 0 ? last.bars[0].realBounds.y : top;
    const w = 78 * (api.settings.display.scale || 1);
    return { x: last.realBounds.x + last.realBounds.w - w, y: top, w, h: Math.max(0, staffTop - top) };
  }

  // Where alphaTab drew its "alphaTab.net" mark, in the page's pixels: the curved outlines of the one path that holds it (the
  // staff lines it rests on are straight). Null when it is not in the engraving.
  function drawnAttribution() {
    const origin = el.getBoundingClientRect();
    for (const path of el.querySelectorAll('svg path')) {
      const d = path.getAttribute('d') || '';
      if (!/[Cc]/.test(d) || path.getBBox().width < 40) continue;
      const probe = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      probe.setAttribute('d', d.split(/(?=M)/).filter((part) => /[Cc]/.test(part)).join(''));
      path.parentNode.appendChild(probe);
      const r = probe.getBoundingClientRect();
      probe.remove();
      if (r.width > 0 && r.height > 0) return { x: r.left - origin.left - 1, y: r.top - origin.top - 1, w: r.width + 2, h: r.height + 2 }; // (a pixel of margin)
    }
    return null;
  }

  // The vertical extent [top, top + height] of a cursor box at x..x+w, kept out of the attribution's zone.
  function clearOfAttribution(x, w, top, height) {
    const z = attribution;
    if (!z || x >= z.x + z.w || x + w <= z.x || top >= z.y + z.h || top + height <= z.y) return { top, height };
    const below = z.y + z.h;
    return { top: below, height: Math.max(0, top + height - below) };
  }

  function measure() {
    beats = new Map(); barBoxes = new Map();
    const lookup = api.boundsLookup;
    if (!lookup) return null;
    attribution = drawnAttribution() || attributionZone(lookup);
    const bars = [];
    for (const sys of lookup.staffSystems) for (const mb of sys.bars) {
      const v = mb.visualBounds;
      const box = { bar: mb.index, x: v.x, y: v.y, w: v.w, h: v.h };
      barBoxes.set(mb.index, box);
      const stops = [];
      const staff = mb.bars.find((b) => b.bar && b.bar.staff && b.bar.staff.index === markStaff) || mb.bars[0];
      if (staff) for (const bb of staff.beats) {
        if (bb.beat.isEmpty) continue;
        stops.push({ tick: bb.beat.playbackStart, x: bb.onNotesX || bb.visualBounds.x, w: bb.visualBounds.w });
      }
      stops.sort((a, b) => a.tick - b.tick);
      beats.set(mb.index, stops);
      bars.push(box);
    }
    const systems = lookup.staffSystems;
    const last = systems[systems.length - 1];
    const height = last ? Math.ceil(last.visualBounds.y + last.visualBounds.h) : 0;
    const lines = [];
    for (const sys of systems) {
      if (sys.bars.length === 0) continue;
      const b = sys.realBounds || sys.visualBounds;
      lines.push({ top: b.y, bottom: b.y + b.h, first: sys.bars[0].index, last: sys.bars[sys.bars.length - 1].index });
    }
    return { height, bars, lines, marks: markBoxes(lookup) };
  }

  let started = 0;

  // Tells the app of the engraving. alphaTab says it has finished before every bar has its bounds: until the page has
  // its bars, this looks again on the next frames, for about a second.
  function publish(tries) {
    const m = measure();
    if ((!m || m.bars.length === 0) && tries < 60) { requestAnimationFrame(() => publish(tries + 1)); return; }
    if (!m) { post({ kind: 'error', message: 'the page has no bounds' }); return; }
    // A mark of the app's under alphaTab's own: the text that keeps its band grows, and the page is engraved again.
    const z = attribution;
    if (z && markText < MARK_TEXT_MAX && m.marks.some((b) => b.x - b.w / 2 < z.x + z.w && z.x < b.x + b.w / 2 && b.top < z.y + z.h && z.y < b.bottom)) {
      markText += MARK_TEXT_STEP;
      markFont(api.settings);
      setTimeout(() => { api.updateSettings(); api.renderScore(score, [0]); }, 0);
      return;
    }
    document.getElementById('page').style.height = m.height + 'px';
    post({ kind: 'rendered', height: m.height, width: el.clientWidth, bars: m.bars, lines: m.lines, marks: m.marks, ms: Math.round(performance.now() - started),
      fonts: [...document.fonts].map((f) => f.family + ':' + f.status) });
  }

  window.tab = {
    // song: base64 MusicXML. opts: {scale, palette, staff ("tab" | "both"), doubtful: ["bar:string:fret:tick"],
    // marks: [{staff, bar, tick, notes: [{string, fret, pitchClass, doubt}]}], markStaff}. In `doubtful` strings are
    // counted from the lowest, as alphaTab counts them; in `marks` from the top line, as the tab's data counts them.
    show(song, opts) {
      doubtful = new Set(opts.doubtful || []);
      marks = opts.marks || [];
      markStaff = opts.markStaff || 0;
      markText = opts.markText || MARK_TEXT_SPACES; // (opts.markText: the starting height, for the tests)
      if (!api) {
        api = new at.AlphaTabApi(el, settings(opts));
        api.error.on((e) => post({ kind: 'error', message: String(e && e.message || e) }));
        api.postRenderFinished.on(() => publish(0));
      } else {
        // every call is a new page: its size and colours too, as its staves (below)
        api.settings.display.scale = opts.scale || 1;
        markFont(api.settings);
        applyPalette(api.settings, opts.palette);
        api.updateSettings();
      }
      started = performance.now();
      const bytes = Uint8Array.from(atob(song), (c) => c.charCodeAt(0));
      score = at.importer.ScoreLoader.loadScoreFromBytes(bytes, api.settings);
      // alphaTab 1.9 numbers only the first bar of each system; the marks stand above the numbers, so every bar has one.
      for (const config of [score.stylesheet.scoreConfig, score.stylesheet.tabConfig, score.stylesheet.slashConfig, score.stylesheet.numberedConfig]) config.barNumber = at.model.BarNumberDisplay.AllBars;
      for (const st of score.tracks[0].staves) {
        const tabStaff = st.isStringed;
        st.showTablature = tabStaff;
        st.showStandardNotation = !tabStaff || opts.staff === 'both';
      }
      musicInTheFirstVoice();
      place();
      tint();
      api.renderScore(score, [0]);
    },

    // The colours of another appearance: the same page engraved again in them.
    palette(p) {
      applyPalette(api.settings, p);
      tint();
      api.updateSettings();
      api.render();
    },

    // The cursor at a beat: bar counted from 0, tick in 960 to a quarter from the bar's start. null hides it.
    cursorAt(bar, tick) {
      if (bar === null) { cursor.style.display = 'none'; beatWash.style.display = 'none'; return null; }
      const box = barBoxes.get(bar);
      const stops = beats.get(bar);
      if (!box || !stops || stops.length === 0) return null;
      let stop = stops[0];
      for (const s of stops) if (s.tick <= tick) stop = s;
      const line = clearOfAttribution(stop.x, 2, box.y, box.h);
      const wash = clearOfAttribution(stop.x - stop.w / 2, stop.w, box.y, box.h);
      cursor.style.cssText = 'display:block;left:' + stop.x + 'px;top:' + line.top + 'px;height:' + line.height + 'px;background:' + palette.cursor;
      beatWash.style.cssText = 'display:block;left:' + (stop.x - stop.w / 2) + 'px;top:' + wash.top + 'px;width:' + stop.w + 'px;height:' + wash.height + 'px;background:' + (palette.cursorTint || 'transparent');
      return { x: stop.x, y: box.y, h: box.h };
    },
  };
  post({ kind: 'ready' });
})();
