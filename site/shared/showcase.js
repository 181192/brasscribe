// What the front pages' figures do when a visitor touches them. Every figure is complete in the HTML;
// this adds the moving parts: the strip under the headline, the steps and the viewers.

const calm = matchMedia("(prefers-reduced-motion: reduce)");
const SVG = "http://www.w3.org/2000/svg";
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);
const make = (name, attributes = {}, parent) => {
  const el = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
  parent?.append(el);
  return el;
};

// What a figure's controls stand at is kept here, so that a change of language, which draws the figure again,
// leaves it as it stood: the same step, tuning, note and place in the recording.
const memory = new Map();
const remember = (el, kind) => {
  const key = `${kind}${[...document.querySelectorAll(`[data-${kind}]`)].indexOf(el)}`;
  if (!memory.has(key)) memory.set(key, {});
  return memory.get(key);
};
// The controls have their place on the page from the start, and are shown once they work.
const ready = (el) => el.querySelectorAll(".await-js").forEach((x) => x.classList.remove("await-js"));

// The strip: sound on the right of the pen, written music on the left. --t is how far it has run, in px.
// Play gives the recording itself, or, with the other button, the notes that were written from it.
function strip(el) {
  const d = JSON.parse(el.dataset.strip);
  const stage = el.querySelector(".strip-stage");
  const range = el.querySelector("input[type=range]");
  const out = el.querySelector("output");
  const button = el.querySelector("[data-strip-play]");
  const hear = [...el.querySelectorAll("[data-hear]")];
  const kept = remember(el, "strip");
  ready(el);
  // `quiet` is the run it makes by itself when it comes into view: no sound, and the button still says Play.
  let t = 0, from = 0, started = 0, playing = false, quiet = false, frame = 0, audio = null, voices = [];
  let mode = kept.mode ?? "recording", recording = null;

  // Tab runs straight in time; engraved notation does not, and brings its own seconds-to-pixels points.
  const px = (seconds) => {
    if (!d.map) return seconds * d.pps;
    const found = d.map.findIndex(([at]) => at >= seconds);
    const i = Math.max(1, found < 0 ? d.map.length - 1 : found);
    const [t0, x0] = d.map[i - 1], [t1, x1] = d.map[i];
    return t1 === t0 ? x1 : x0 + ((x1 - x0) * (Math.min(seconds, t1) - t0)) / (t1 - t0);
  };
  const set = (seconds, byHand) => {
    t = kept.t = Math.max(0, Math.min(d.dur, seconds));
    stage.style.setProperty("--t", px(t).toFixed(1));
    if (!byHand) range.value = t;
    const beat = Math.max(0, d.beats.findLastIndex((b) => b <= t));
    out.textContent = d.barBeat.replace("{bar}", Math.floor(beat / d.perBar) + 1).replace("{beat}", (beat % d.perBar) + 1);
    range.setAttribute("aria-valuetext", out.textContent);
  };
  const stop = () => {
    playing = quiet = false;
    cancelAnimationFrame(frame);
    recording?.pause();
    for (const v of voices) try { v.stop(); } catch {}
    voices = [];
    button.textContent = d.play;
  };
  // The notes that were written, as plain tones: a way to hear what is on the page beside the recording.
  const written = () => {
    audio ??= new AudioContext();
    audio.resume();
    const now = audio.currentTime + 0.05;
    for (const [on, length, pitch] of d.notes) {
      if (on < t - 0.05) continue;
      const at = now + on - t, hold = Math.max(0.3, length);
      const gain = audio.createGain();
      gain.gain.setValueAtTime(0.0001, at);
      if (d.voice === "brass") {
        // Blown, not plucked: the note holds until it ends.
        gain.gain.exponentialRampToValueAtTime(0.1, at + 0.04);
        gain.gain.setValueAtTime(0.1, at + hold - 0.06);
      } else gain.gain.exponentialRampToValueAtTime(0.2, at + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + hold);
      gain.connect(audio.destination);
      // A low note is below what a phone's speaker gives: its octave sounds along.
      for (const [octave, type] of [[1, "triangle"], [2, "sine"]]) {
        const osc = audio.createOscillator();
        osc.type = type;
        osc.frequency.value = 440 * 2 ** ((pitch - 69) / 12) * octave;
        osc.connect(gain);
        osc.start(at);
        osc.stop(at + hold + 0.05);
        voices.push(osc);
      }
    }
  };
  const run = (now) => {
    // The recording keeps its own time; without it the clock does.
    set(playing && !quiet && mode === "recording" && recording && !recording.paused ? recording.currentTime : from + (now - started) / 1000);
    if (t >= d.dur) return stop();
    frame = requestAnimationFrame(run);
  };
  const play = (withSound) => {
    if (t >= d.dur - 0.05) set(0);
    playing = true;
    quiet = !withSound;
    from = t;
    started = performance.now();
    if (withSound) {
      button.textContent = d.pause;
      if (mode === "recording" && el.dataset.audio) {
        recording ??= new Audio(new URL(el.dataset.audio, location.href));
        recording.currentTime = t;
        recording.play().catch(() => {});
      } else written();
    }
    frame = requestAnimationFrame(run);
  };
  button.addEventListener("click", () => {
    kept.touched = true;
    if (playing && !quiet) return stop();
    // During the quiet run the button says Play, and Play it is: sound from where the strip is now.
    if (playing) stop();
    play(true);
  });
  for (const b of hear) {
    b.addEventListener("click", () => {
      const was = playing && !quiet;
      if (playing) stop();
      mode = kept.mode = b.dataset.hear;
      hear.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      if (was) play(true);
    });
  }
  range.addEventListener("input", () => {
    if (playing) stop();
    kept.touched = true;
    set(+range.value, true);
  });
  document.addEventListener("visibilitychange", () => document.hidden && playing && stop());
  // When the language changes, the strip is drawn again: this one must fall silent.
  document.addEventListener("scribe:lang", () => !el.isConnected && stop());

  // Once, when it comes into view, it writes itself out without sound. Not when motion is unwanted.
  hear.forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.hear === mode)));
  set(kept.touched ? kept.t : calm.matches ? d.dur * 0.4 : 0);
  if (!calm.matches && !kept.touched) {
    const seen = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      seen.disconnect();
      if (!playing && t === 0) play(false);
    }, { threshold: 0.6 });
    seen.observe(stage);
  }
}

// The steps: one at a time. A ruled line with a mark for each step and the pen on the one that is shown.
function stages(list) {
  const items = [...list.children];
  const nav = document.createElement("div");
  nav.className = "stages-nav";
  nav.setAttribute("role", "group");
  nav.setAttribute("aria-label", list.dataset.steps);
  const buttons = items.map((item, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = i + 1;
    b.setAttribute("aria-label", `${i + 1}: ${item.querySelector("h3").textContent}`);
    b.addEventListener("click", () => show(i));
    nav.append(b);
    return b;
  });
  const step = (label, by) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button outline";
    b.textContent = label;
    // It stays focusable at either end, so the keyboard does not lose its place.
    b.addEventListener("click", () => b.getAttribute("aria-disabled") !== "true" && show(current + by));
    return b;
  };
  const previous = step(list.dataset.previous, -1), next = step(list.dataset.next, 1);
  const foot = document.createElement("div");
  foot.className = "stages-foot";
  foot.append(previous, next);
  const kept = remember(list, "stages");
  let current = kept.step ?? 0;
  const show = (i) => {
    current = kept.step = Math.max(0, Math.min(items.length - 1, i));
    items.forEach((item, k) => (item.hidden = k !== current));
    buttons.forEach((b, k) => {
      if (k === current) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
      b.classList.toggle("done", k < current);
    });
    nav.style.setProperty("--at", items.length > 1 ? current / (items.length - 1) : 0);
    previous.setAttribute("aria-disabled", String(current === 0));
    next.setAttribute("aria-disabled", String(current === items.length - 1));
  };
  // The buttons stand over the step, so they stay where they are when a taller or a shorter step comes.
  list.setAttribute("aria-live", "polite");
  list.before(nav, foot);
  // The list keeps the height of its tallest step, so what follows it stays where it is.
  const settle = () => {
    list.style.minHeight = "";
    items.forEach((item) => (item.hidden = false));
    list.classList.remove("live");
    const tallest = Math.max(...items.map((item) => item.offsetHeight));
    list.classList.add("live");
    list.style.minHeight = `${tallest}px`;
    show(current);
  };
  settle();
  let width = innerWidth;
  addEventListener("resize", () => width !== innerWidth && ((width = innerWidth), settle()));
  document.fonts?.ready.then(settle);
}

// The tab viewer: the same notes in another tuning, as the core's solver placed them, and for the note that
// is chosen a small neck with every place it can be played.
async function tabdemo(el) {
  const config = JSON.parse(el.dataset.tabdemo), w = config.words;
  const demo = await (await fetch(el.dataset.src)).json();
  const tuning = el.querySelector("[data-tuning]"), capo = el.querySelector("[data-capo]");
  const status = el.querySelector("[data-status]"), neck = el.querySelector("[data-neck]");
  const scroll = el.querySelector(".tabdemo-scroll"), svg = scroll.querySelector("svg");
  const notes = [...svg.querySelectorAll("g.note")];
  const x = notes.map((g) => g.getAttribute("transform").match(/translate\(([\d.]+)/)[1]);
  const perBeat = demo.ticks_per_beat, perBar = demo.meter.beats * perBeat;
  let variant = demo.variants[demo.default], chosen = -1;
  const kept = remember(el, "tabdemo");
  ready(el);
  // A note that no tuning here has a place for: a sound that was heard, not a note that was played.
  const nowhere = demo.notes.map((_, i) => Object.values(demo.variants).every((v) => v.places[i][2]));

  const where = (string, fret) => fill(w.place, { string: w.ordinals[string - 1], fret });
  const at = (i) => {
    const [pitch, start] = demo.notes[i];
    return fill(w.at, { bar: Math.floor(start / perBar) + 1, beat: Math.floor((start % perBar) / perBeat) + 1, name: w.names[pitch % 12] });
  };
  const others = (place) => {
    const list = [];
    for (let k = 3; k < place.length; k += 2) list.push([place[k], place[k + 1]]);
    return list;
  };
  const describe = (i) => {
    const place = variant.places[i], also = others(place).map(([s, f]) => where(s, f));
    if (place[2]) return `${at(i)} ${nowhere[i] ? w.nowhere : w.lost}`;
    // The solver can leave a note out of a fingering though the neck has a place for it.
    if (place[0] === null) return `${at(i)} ${w.left} ${also.length ? fill(w.could, { places: also.join(w.or) }) : ""}`.trim();
    const doubt = demo.notes[i][3] ? ` ${w.doubt}` : "";
    return `${at(i)} ${where(place[0], place[1])}.${doubt} ${also.length ? fill(w.also, { places: also.join(w.or) }) : w.only}`;
  };
  // The neck: a line for each string, the chosen place filled, the other places as rings.
  const drawNeck = (i) => {
    const place = variant.places[i], spots = others(place);
    neck.hidden = place[2] === 1 || (place[0] === null && !spots.length);
    if (neck.hidden) return;
    // one fret more than the highest place, so no dot sits on the picture's edge
    const strings = variant.open.length, frets = Math.max(12, ...spots.map(([, f]) => f), place[1] ?? 0) + 1;
    const fw = 22, top = 12, gap = 13, left = 26, width = left + frets * fw + 12, height = top + gap * (strings - 1) + 26;
    const picture = make("svg", { viewBox: `0 0 ${width} ${height}`, width, height, class: "tab-ink neck-ink", role: "img", "aria-label": w.neck });
    for (let f = 0; f <= frets; f++) make("path", { class: f === 0 ? "nut" : "fret-wire", d: `M${left + f * fw} ${top}V${top + gap * (strings - 1)}` }, picture);
    for (let s = 0; s < strings; s++) make("path", { class: "string", d: `M${left - 14} ${top + gap * s}H${left + frets * fw}` }, picture);
    for (const f of [3, 5, 7, 9, 12, 15, 17, 19, 21].filter((n) => n <= frets)) {
      make("text", { class: "bar-no", x: left + (f - 0.5) * fw, y: height - 4, "text-anchor": "middle" }, picture).textContent = f;
    }
    const dot = (string, fret, kind) => make("circle", { class: kind, cx: fret === 0 ? left - 8 : left + (fret - 0.5) * fw, cy: top + gap * (string - 1), r: 5 }, picture);
    for (const [s, f] of spots) dot(s, f, "other");
    if (place[0] !== null) dot(place[0], place[1], "here");
    neck.replaceChildren(picture);
  };
  const draw = () => {
    variant = demo.variants[`${tuning.value}/${capo ? capo.value : 0}`];
    kept.tuning = tuning.value;
    kept.capo = capo?.value;
    let lost = 0, left = 0;
    notes.forEach((g, i) => {
      const [string, fret, gone] = variant.places[i];
      const out = gone ? "!" : string === null ? "–" : "";
      lost += gone;
      left += !gone && string === null;
      g.setAttribute("transform", `translate(${x[i]} ${out ? config.bottom + 30 : config.top + config.gap * (string - 1)})`);
      g.classList.toggle("lost", !!out);
      g.querySelector("text").textContent = out || fret;
      g.setAttribute("aria-label", out ? `${at(i)} ${out}` : `${at(i)} ${where(string, fret)}`);
    });
    svg.setAttribute("aria-label", fill(config.label, { title: config.title, bars: config.bars, tuning: variant.tuning }));
    const summary = fill(lost > 1 ? w.summary_lost : lost ? w.summary_lost_one : w.summary,
      { tuning: variant.tuning, lost })
      + (left ? " " + fill(w.summary_left, { left }) : "");
    status.textContent = chosen < 0 ? summary : describe(chosen);
    if (chosen >= 0) drawNeck(chosen);
  };
  const choose = (i, focus) => {
    chosen = kept.chosen = i;
    notes.forEach((g, k) => {
      g.classList.toggle("chosen", k === i);
      g.setAttribute("aria-pressed", String(k === i));
      g.tabIndex = k === i ? 0 : -1;
    });
    if (focus) notes[i].focus({ preventScroll: true });
    // The chosen note is brought whole into the scroller, wherever the arrow keys took it.
    const box = notes[i].getBoundingClientRect(), frame = scroll.getBoundingClientRect();
    if (box.left < frame.left + 16 || box.right > frame.right - 16) {
      scroll.scrollBy({ left: box.left + box.width / 2 - (frame.left + frame.width / 2), behavior: calm.matches ? "auto" : "smooth" });
    }
    draw();
  };
  notes.forEach((g, i) => {
    g.setAttribute("role", "button");
    g.setAttribute("aria-pressed", "false");
    g.tabIndex = i === 0 ? 0 : -1;
    g.addEventListener("click", () => choose(i, true));
    g.addEventListener("keydown", (e) => {
      const by = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (by) choose(Math.max(0, Math.min(notes.length - 1, i + by)), true);
      else if (e.key === "Enter" || e.key === " ") choose(i, true);
      else return;
      e.preventDefault();
    });
  });
  // The drawing is a group of buttons now, no longer one picture.
  svg.setAttribute("role", "group");
  tuning.addEventListener("change", draw);
  capo?.addEventListener("change", draw);
  // After a change of language it stands as it stood.
  const before = kept.chosen;
  if (kept.tuning) tuning.value = kept.tuning;
  if (capo && kept.capo) capo.value = kept.capo;
  draw();
  if (before !== undefined) choose(before, false);
}

// The part viewer: every player's part under each other, or one of them alone, and for the note that is chosen
// what it is, in words.
async function partview(el) {
  const config = JSON.parse(el.dataset.partview), w = config.words, lang = config.lang, kept = remember(el, "partview");
  const score = await (await fetch(el.dataset.src + "score.json")).json();
  const select = el.querySelector("[data-part]"), status = el.querySelector("[data-status]"), scroll = el.querySelector(".tabdemo-scroll");
  const drawings = [...scroll.querySelectorAll("svg[data-part]")];
  const all = score.parts.flatMap((part) => part.notes.map((n) => n[3])).filter(Boolean).length;
  let notes = [];
  ready(el);
  const said = (part, n) => {
    const [, , , doubt, bar, beat, within, step, alter, type, dots, tied] = n;
    const pitch = (alter > 0 ? w.sharp : alter < 0 ? w.flat : w.natural)["CDEFGAB".indexOf(step)];
    const value = dots ? fill(w.dotted, { value: w[`value_${type}`] }) : w[`value_${type}`];
    return fill(w.said, { name: part.name[lang], bar, beat: fill(within === "0/1" ? w.beat : w.beat_half, { beat }), pitch, value,
      tied: tied ? w.tied : "", doubt: doubt ? w.doubt : "" });
  };
  const summary = () => {
    const part = score.parts.find((p) => p.id === select.value);
    if (!part) return fill(w.start_all, { n: score.parts.length, doubt: all });
    const doubt = part.notes.filter((n) => n[3]).length;
    return fill(w.start, { name: part.name[lang], instrument: part.instrument[lang], doubt: doubt ? fill(w.some, { n: doubt }) : w.none });
  };
  const choose = (i, focus) => {
    kept.chosen = i;
    notes.forEach(({ g }, k) => {
      g.classList.toggle("chosen", k === i);
      g.setAttribute("aria-pressed", String(k === i));
      g.tabIndex = k === i ? 0 : -1;
    });
    const { g, text } = notes[i];
    if (focus) g.focus({ preventScroll: true });
    // The chosen note is brought whole into the scroller, wherever the arrow keys took it.
    const box = g.getBoundingClientRect(), frame = scroll.getBoundingClientRect();
    if (box.left < frame.left + 16 || box.right > frame.right - 16) {
      scroll.scrollBy({ left: box.left + box.width / 2 - (frame.left + frame.width / 2), behavior: calm.matches ? "auto" : "smooth" });
    }
    status.textContent = text;
  };
  // Every note of every part is a button, once; which of them can be reached follows the parts that are shown.
  const every = drawings.flatMap((svg) => {
    const part = score.parts.find((p) => p.id === svg.dataset.part);
    svg.setAttribute("role", "group");
    return [...svg.querySelectorAll("g.note")].map((g, i) => {
      // A note is a small thing to hit: its whole box, and a little more, takes the pointer.
      const box = g.getBBox(), text = said(part, part.notes[i]);
      g.prepend(make("rect", { x: box.x - 90, y: box.y - 90, width: box.width + 180, height: box.height + 180, rx: 60, class: "hit" }));
      g.setAttribute("role", "button");
      g.setAttribute("aria-pressed", "false");
      g.setAttribute("aria-label", text);
      const note = { g, text, svg };
      g.addEventListener("click", () => choose(notes.indexOf(note), true));
      g.addEventListener("keydown", (e) => {
        const i = notes.indexOf(note), by = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (by) choose(Math.max(0, Math.min(notes.length - 1, i + by)), true);
        else if (e.key === "Enter" || e.key === " ") choose(i, true);
        else return;
        e.preventDefault();
      });
      return note;
    });
  });
  const show = () => {
    kept.part = select.value;
    for (const svg of drawings) svg.style.display = select.value === "all" || svg.dataset.part === select.value ? "" : "none";
    notes = every.filter(({ svg }) => svg.style.display !== "none");
    every.forEach(({ g }) => {
      g.classList.remove("chosen");
      g.setAttribute("aria-pressed", "false");
      g.tabIndex = -1;
    });
    if (notes.length) notes[0].g.tabIndex = 0;
    status.textContent = summary();
  };
  select.addEventListener("change", () => {
    delete kept.chosen;
    show();
  });
  // After a change of language it stands as it stood: the same part, the same note.
  const chosen = kept.chosen;
  if (kept.part) select.value = kept.part;
  show();
  if (chosen !== undefined && notes[chosen]) choose(chosen, false);
}

// Everything in a part of the page that can be played with. The whole page at first; after the language changes,
// the parts whose words were swapped, which are new elements.
const within = (root, selector) => [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)];
function enhance(root) {
  const lazily = (selector, make) => within(root, selector).forEach((el) => {
    // A viewer's data is fetched when it is about to be seen.
    const near = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      near.disconnect();
      make(el).catch(() => {});
    }, { rootMargin: "600px" });
    near.observe(el);
  });
  within(root, "[data-strip]").forEach(strip);
  within(root, "[data-stages]").forEach(stages);
  lazily("[data-tabdemo]", tabdemo);
  lazily("[data-partview]", partview);
}
enhance(document);
document.addEventListener("scribe:lang", (e) => e.detail.replaced.forEach(enhance));
