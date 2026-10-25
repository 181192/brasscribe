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
  let placed = []; // [{mark: index into marks, beat, doubtful: [Note]}]
  const MARK_SPACE = ' '; // the blank text of a marked beat: alphaTab keeps a band above the staff for it
  const MARK_LINE_SPACES = 1.4; // a mark's height in tab line spaces

  window.onerror = (msg, src, line) => post({ kind: 'error', message: String(msg) + ' (' + src + ':' + line + ')' });

  function hidden() {
    const e = at.NotationElement;
    return [e.ScoreTitle, e.ScoreSubTitle, e.ScoreArtist, e.ScoreAlbum, e.ScoreWords, e.ScoreMusic,
      e.ScoreWordsAndMusic, e.ScoreCopyright, e.TrackNames, e.GuitarTuning, e.EffectTempo];
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
    s.display.justifyLastSystem = false;
    s.player.playerMode = at.PlayerMode.Disabled;
    s.player.enableCursor = false;
    s.player.enableUserInteraction = false;
    s.player.scrollMode = at.ScrollMode.Off;
    s.notation.rhythmMode = at.TabRhythmMode.ShowWithBars;
    for (const e of hidden()) s.notation.elements.set(e, false);
    const r = s.display.resources;
    // A marked beat gets blank text, and alphaTab keeps a band above the staff for a line's text: with the text as tall
    // as a mark, the band is the room the marks need, on the lines that have marks and on no others. The band is lifted
    // by a bar number, so a mark stands above the bar's number.
    try {
      const text = r.elementFonts.get(at.NotationElement.EffectText);
      if (text) {
        const family = text.families ? text.families[0] : text.family;
        r.elementFonts.set(at.NotationElement.EffectText, new at.model.Font(family, MARK_LINE_SPACES * lineSpacing(s), text.style, text.weight));
      }
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

  function measure() {
    beats = new Map(); barBoxes = new Map();
    const lookup = api.boundsLookup;
    if (!lookup) return null;
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
      if (!api) {
        api = new at.AlphaTabApi(el, settings(opts));
        api.error.on((e) => post({ kind: 'error', message: String(e && e.message || e) }));
        api.postRenderFinished.on(() => publish(0));
      } else {
        // every call is a new page: its size and colours too, as its staves (below)
        api.settings.display.scale = opts.scale || 1;
        applyPalette(api.settings, opts.palette);
        api.updateSettings();
      }
      started = performance.now();
      const bytes = Uint8Array.from(atob(song), (c) => c.charCodeAt(0));
      score = at.importer.ScoreLoader.loadScoreFromBytes(bytes, api.settings);
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
      cursor.style.cssText = 'display:block;left:' + stop.x + 'px;top:' + box.y + 'px;height:' + box.h + 'px;background:' + palette.cursor;
      beatWash.style.cssText = 'display:block;left:' + (stop.x - stop.w / 2) + 'px;top:' + box.y + 'px;width:' + stop.w + 'px;height:' + box.h + 'px;background:' + (palette.cursorTint || 'transparent');
      return { x: stop.x, y: box.y, h: box.h };
    },
  };
  post({ kind: 'ready' });
})();
