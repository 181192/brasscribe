// The tab page's side of TabPage.swift. The app tells it the song and its colours (show), where the cursor stands
// (cursorAt) and how the screen looks (palette); it answers with the engraving: the page's height and where each bar
// and each beat is, in CSS pixels, so the app can place its own controls and read out the bars.
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
    applyPalette(s, opts.palette);
    return s;
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
        if (doubtful.has(beat.voice.bar.index + ':' + n.string + ':' + n.fret + ':' + beat.playbackStart)) {
          const style = new at.model.NoteStyle();
          for (const e of subs) style.colors.set(e, doubt);
          n.style = style;
        }
      }
  }

  let doubtful = new Set();

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
      const staff = mb.bars[0];
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
    return { height, bars };
  }

  let started = 0;

  // Tells the app of the engraving. alphaTab says it has finished before every bar has its bounds: until the page has
  // its bars, this looks again on the next frames, for about a second.
  function publish(tries) {
    const m = measure();
    if ((!m || m.bars.length === 0) && tries < 60) { requestAnimationFrame(() => publish(tries + 1)); return; }
    if (!m) { post({ kind: 'error', message: 'the page has no bounds' }); return; }
    document.getElementById('page').style.height = m.height + 'px';
    post({ kind: 'rendered', height: m.height, width: el.clientWidth, bars: m.bars, ms: Math.round(performance.now() - started),
      fonts: [...document.fonts].map((f) => f.family + ':' + f.status) });
  }

  window.tab = {
    // song: base64 MusicXML. opts: {scale, palette, staff ("tab" | "both"), doubtful: ["bar:string:fret:tick"]}
    show(song, opts) {
      doubtful = new Set(opts.doubtful || []);
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
