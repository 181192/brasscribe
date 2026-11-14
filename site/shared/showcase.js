// What the front pages' figures do when a visitor touches them. Every figure is complete in the HTML;
// this adds the moving parts: the strip under the headline, the steps and the viewers.

const calm = matchMedia("(prefers-reduced-motion: reduce)");
// Here to move what moves (early.js puts a page at rest when no script says so).
document.documentElement.classList.add("moving");
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

// One sound at a time on the whole page: what starts to play says so, and everything else falls silent.
const sounding = (stop) => document.dispatchEvent(new CustomEvent("scribe:sound", { detail: stop }));
const quietFor = (stop) => document.addEventListener("scribe:sound", (e) => e.detail !== stop && stop());

// Segmented buttons in place of a list to pick from, as a group of radio buttons: the checked one is the value, Tab
// reaches only it, and the arrow keys move the choice.
function segmented(group, changed) {
  const buttons = [...group.querySelectorAll("button[data-value]")];
  // On a phone the row scrolls: the checked one is brought into it (the row moves, not the page), and a fade on a
  // side says there is more that way.
  const edges = () => {
    group.classList.toggle("more-before", group.scrollLeft > 1);
    group.classList.toggle("more-after", group.scrollLeft + group.clientWidth < group.scrollWidth - 1);
  };
  const reveal = (b) => {
    const row = group.getBoundingClientRect(), box = b.getBoundingClientRect();
    if (box.left < row.left) group.scrollLeft -= row.left - box.left + 24;
    else if (box.right > row.right) group.scrollLeft += box.right - row.right + 24;
    edges();
  };
  group.addEventListener("scroll", edges, { passive: true });
  addEventListener("resize", edges);
  requestAnimationFrame(edges);
  const control = {
    get value() { return buttons.find((b) => b.getAttribute("aria-checked") === "true")?.dataset.value; },
    set value(v) {
      buttons.forEach((b) => {
        b.setAttribute("aria-checked", String(b.dataset.value === v));
        b.tabIndex = b.dataset.value === v ? 0 : -1;
        if (b.dataset.value === v) reveal(b);
      });
    },
  };
  const pick = (b) => {
    if (b.dataset.value === control.value) return;
    control.value = b.dataset.value;
    changed();
  };
  buttons.forEach((b, i) => {
    b.addEventListener("click", () => pick(b));
    b.addEventListener("keydown", (e) => {
      const by = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      const to = by ? buttons[(i + by + buttons.length) % buttons.length] : { Home: buttons[0], End: buttons.at(-1) }[e.key];
      if (!to) return;
      e.preventDefault();
      to.focus({ preventScroll: true });
      pick(to);
    });
  });
  control.value = control.value;
  return control;
}

// Sound comes in and goes out over a few milliseconds, so starting and stopping it does not click.
const FADE = 0.015;
const ramp = (gain, to) => {
  const now = gain.context.currentTime;
  gain.gain.cancelScheduledValues(now);
  gain.gain.setValueAtTime(gain.gain.value, now);
  gain.gain.linearRampToValueAtTime(to, now + FADE);
};
// The recording, played through the page's sound so it can fade. Made on the first Play, not before.
function recording(src) {
  const audio = new Audio(new URL(src, location.href));
  let gain = null, run = 0;
  return {
    audio,
    play() {
      const mine = ++run, from = audio.currentTime;
      context ??= new AudioContext();
      const waking = context.state === "running" ? null : context.resume();
      if (!gain) {
        gain = context.createGain();
        context.createMediaElementSource(audio).connect(gain).connect(context.destination);
      }
      gain.gain.cancelScheduledValues(context.currentTime);
      gain.gain.setValueAtTime(0, context.currentTime);
      ramp(gain, 1);
      // play() is called at once, while the tap still counts as one (a phone wants that). The page's sound may be
      // slow to wake, and the recording runs on muted meanwhile: once it is awake, it starts again from the start.
      waking?.then(() => {
        if (mine !== run) return;
        audio.currentTime = from;
        gain.gain.cancelScheduledValues(context.currentTime);
        gain.gain.setValueAtTime(0, context.currentTime);
        ramp(gain, 1);
      });
      return audio.play();
    },
    pause() {
      if (!gain || audio.paused) return audio.pause();
      const mine = ++run;
      ramp(gain, 0);
      setTimeout(() => mine === run && audio.pause(), FADE * 1000 + 10);
    },
  };
}

// The notes that were written, as plain tones: a way to hear what is on the page beside the recording. `notes` are
// [start, length, pitch] in seconds; they sound from `from` on. Gives back what stops them.
let context = null;
function synth(notes, from, voice) {
  context ??= new AudioContext();
  context.resume();
  const now = context.currentTime + 0.05, voices = [], all = context.createGain();
  all.connect(context.destination);
  for (const [on, length, pitch] of notes) {
    if (on < from - 0.05) continue;
    const at = now + on - from, hold = Math.max(0.3, length);
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.0001, at);
    if (voice === "brass") {
      // Blown, not plucked: the note holds until it ends.
      gain.gain.exponentialRampToValueAtTime(0.1, at + 0.04);
      gain.gain.setValueAtTime(0.1, at + hold - 0.06);
    } else gain.gain.exponentialRampToValueAtTime(0.2, at + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + hold);
    gain.connect(all);
    // A low note is below what a phone's speaker gives: its octave sounds along.
    for (const [octave, type] of [[1, "triangle"], [2, "sine"]]) {
      const osc = context.createOscillator();
      osc.type = type;
      osc.frequency.value = 440 * 2 ** ((pitch - 69) / 12) * octave;
      osc.connect(gain);
      osc.start(at);
      osc.stop(at + hold + 0.05);
      voices.push(osc);
    }
  }
  const last = Math.max(0, ...notes.map(([on, length]) => on + Math.max(0.3, length))) - from;
  const stop = () => {
    ramp(all, 0);
    const end = context.currentTime + FADE + 0.01;
    voices.forEach((v) => { try { v.stop(end); } catch {} });
  };
  return { stop, seconds: last };
}

// A Play button for a stretch of the recording or for written notes: Play again stops it, it stops by itself at
// the end, and it falls silent when anything else on the page starts to sound.
// `status` (when there is one) says so when the recording cannot be played.
function player(button, src, words, status) {
  let audio = null, timer = 0, tones = null, playing = false;
  const stop = () => {
    playing = false;
    audio?.pause();
    tones?.stop();
    clearInterval(timer);
    clearTimeout(timer);
    button.textContent = words.play;
  };
  quietFor(stop);
  document.addEventListener("visibilitychange", () => document.hidden && stop());
  // When the language changes, the button is made again: the old one must fall silent.
  document.addEventListener("scribe:lang", () => !button.isConnected && stop());
  const failed = () => {
    stop();
    if (status) status.textContent = words.failed;
    else button.textContent = words.failed;
  };
  const start = () => {
    playing = true;
    sounding(stop);
    button.textContent = words.pause;
  };
  return {
    stop,
    // The recording from one second to another.
    range(from, to) {
      if (playing) return stop();
      audio ??= recording(src);
      audio.audio.currentTime = from;
      start();
      audio.play().catch(failed);
      timer = setInterval(() => audio.audio.currentTime >= to - 0.02 && stop(), 40);
    },
    // The written notes, from the first.
    notes(list, voice) {
      if (playing) return stop();
      start();
      tones = synth(list, list.length ? Math.min(...list.map(([on]) => on)) : 0, voice);
      timer = setTimeout(stop, tones.seconds * 1000 + 200);
    },
  };
}

// The plain-text tab of a tuning, from the tab viewer's data: two bars a line, a column for every third of a
// sixteenth (as the engine writes its .txt), a "?" over a doubted note.
function plainTab(demo, variant, frame) {
  const names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"];
  const perBar = demo.meter.beats * demo.ticks_per_beat, step = demo.ticks_per_beat / 8, width = perBar / step;
  const last = Math.max(...demo.notes.map(([, start, dur]) => start + dur));
  const bars = Math.ceil(last / perBar), strings = variant.open.length;
  const lines = frame.head.map((l) => l.startsWith("Tuning:")
    ? `Tuning: ${variant.tuning} (${[...variant.open].reverse().map((p) => names[p % 12]).join(" ")}), bottom line to top` : l);
  for (let first = 0; first < bars; first += 2) {
    const shown = [first, first + 1].filter((b) => b < bars);
    const rows = Array.from({ length: strings }, () => []), marks = [];
    let numbers = "";
    for (const b of shown) {
      const end = b === bars - 1 ? Math.max(...demo.notes.filter(([, s]) => s >= b * perBar).map(([, s]) => Math.round((s - b * perBar) / step))) + 8 : width;
      const cells = Array.from({ length: strings }, () => Array(end).fill("-")), doubt = Array(end).fill(" ");
      demo.notes.forEach(([, start, , doubted], i) => {
        if (start < b * perBar || start >= (b + 1) * perBar) return;
        const [string, fret] = variant.places[i];
        if (string === null) return;
        const col = 1 + Math.round((start - b * perBar) / step);
        String(fret).split("").forEach((ch, k) => (cells[string - 1][col + k] = ch));
        if (doubted) doubt[col] = "?";
      });
      numbers += String(b + 1).padEnd(end + 1);
      marks.push(" " + doubt.join(""));
      cells.forEach((c, s) => rows[s].push(c.join("")));
    }
    lines.push("", "  " + numbers.trimEnd());
    const mark = marks.join("");
    if (mark.trim()) lines.push(" " + mark.trimEnd());
    const end = shown.at(-1) === bars - 1 ? "||" : "|";
    rows.forEach((r, s) => lines.push(`${names[variant.open[s] % 12]}|${r.join("|")}${end}`));
  }
  return [...lines, ...frame.foot].join("\n");
}

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
  let t = 0, from = 0, started = 0, playing = false, quiet = false, frame = 0, voices = [];
  let mode = kept.mode ?? "recording", sound = null;

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
    // The engine's first downbeat is below 0 when the take starts with an upbeat: its first beat is not beat 1.
    const k = beat - (d.first ?? 0);
    out.textContent = d.barBeat.replace("{bar}", Math.floor(k / d.perBar) + 1).replace("{beat}", (k % d.perBar) + 1);
    range.setAttribute("aria-valuetext", out.textContent);
  };
  const stop = () => {
    playing = quiet = false;
    cancelAnimationFrame(frame);
    sound?.pause();
    for (const v of voices) v.stop();
    voices = [];
    button.textContent = d.play;
  };
  // Another sound on the page starts: a strip that is sounding stops; one that writes itself out quietly goes on.
  const hush = () => playing && !quiet && stop();
  // The notes that were written, as plain tones, from where the pen is.
  const written = () => voices.push(synth(d.notes, t, d.voice));
  const run = (now) => {
    // The recording keeps its own time; without it the clock does.
    set(playing && !quiet && mode === "recording" && sound && !sound.audio.paused ? sound.audio.currentTime : from + (now - started) / 1000);
    if (t >= d.dur) {
      // At the end of the quiet run, Play says once that there is sound to hear.
      if (quiet) {
        button.classList.add("nudge");
        button.addEventListener("animationend", () => button.classList.remove("nudge"), { once: true });
      }
      return stop();
    }
    frame = requestAnimationFrame(run);
  };
  const play = (withSound) => {
    if (t >= d.dur - 0.05) set(0);
    playing = true;
    quiet = !withSound;
    from = t;
    started = performance.now();
    if (withSound) {
      sounding(hush);
      button.textContent = d.pause;
      if (mode === "recording" && el.dataset.audio) {
        sound ??= recording(el.dataset.audio);
        sound.audio.currentTime = t;
        sound.play().catch(() => {});
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
  // A tap on the strip moves the pen there: to the left, back into what was written; to the right, on in the sound.
  const at = (x) => {
    if (!d.map) return x / d.pps;
    let lo = 0, hi = d.dur;
    for (let k = 0; k < 30; k++) { const mid = (lo + hi) / 2; if (px(mid) < x) lo = mid; else hi = mid; }
    return lo;
  };
  stage.addEventListener("click", (e) => {
    const box = stage.getBoundingClientRect(), pen = box.left + parseFloat(getComputedStyle(stage).getPropertyValue("--pen")) / 100 * box.width;
    kept.touched = true;
    const was = playing && !quiet;
    if (playing) stop();
    set(at(px(t) + e.clientX - pen));
    if (was) play(true);
  });
  range.addEventListener("input", () => {
    if (playing) stop();
    kept.touched = true;
    set(+range.value, true);
  });
  document.addEventListener("visibilitychange", () => document.hidden && playing && stop());
  quietFor(hush);
  // When the language changes, the strip is drawn again: this one must fall silent.
  document.addEventListener("scribe:lang", () => !el.isConnected && stop());

  // Once, when at least half of it is in view, it writes itself out without sound, and not again: not when it comes
  // back into view, nor after a change of language. Not when motion is unwanted. On the family home the pen comes down
  // from the headline first: when the headline's line is drawn (rail.js says so), the pen's line on each sheet's
  // strip draws, the first sheet's, then the second's, and the strip runs.
  hear.forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.hear === mode)));
  // (Once in half an hour: early.js marks the page "played" when a strip of it has written itself out.)
  const played = document.documentElement.classList.contains("played");
  set(kept.touched || kept.traced ? kept.t : calm.matches || played ? d.dur * 0.4 : 0);
  const sheet = el.closest(".app");
  if (calm.matches || played || kept.touched || kept.traced) el.classList.add("inked");
  else {
    const run = () => {
      el.classList.add("inked");
      setTimeout(() => {
        if (playing || t !== 0) return;
        kept.traced = true;
        try { localStorage.setItem(`scribe-played:${location.pathname}`, String(Date.now())); } catch {}
        play(false);
      }, sheet ? 340 : 0);
    };
    const seen = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      seen.disconnect();
      if (!sheet) return run();
      const after = () => setTimeout(run, 160 * Math.max(0, [...document.querySelectorAll(".app .strip")].indexOf(el)));
      if (document.documentElement.hasAttribute("data-penned")) return after();
      // (The headline may be out of view, a page opened further down: the strip does not wait long for it.)
      let gone = false;
      const once = () => !gone && ((gone = true), after());
      document.addEventListener("scribe:penned", once, { once: true });
      setTimeout(once, 900);
    }, { threshold: 0.5 });
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
  // A step that can be heard has its Play: the recording, the line that was written, or every part.
  const sound = list.dataset.sound && JSON.parse(list.dataset.sound);
  const players = [];
  for (const button of list.querySelectorAll("[data-stage-play]")) {
    const play = sound.plays[button.dataset.stagePlay], p = player(button, list.dataset.audio, sound);
    players.push(p);
    button.addEventListener("click", () => (play.notes ? p.notes(play.notes, play.voice) : p.range(play.from, play.to)));
  }
  ready(list);
  const show = (i) => {
    players.forEach((p) => p.stop());
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
  const tuning = segmented(el.querySelector("[data-tuning]"), () => draw()), capo = el.querySelector("[data-capo]");
  const status = el.querySelector("[data-status]"), neck = el.querySelector("[data-neck]");
  const playBar = el.querySelector("[data-bar-play]"), bar = player(playBar, el.dataset.audio, config, status);
  const plain = el.querySelector("[data-plain]"), asText = el.querySelector("[data-as-text]");
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
    // The plain text is the tab that is shown: in the tuning that is chosen.
    plain.textContent = plainTab(demo, variant, config.text);
    asText.textContent = fill(config.asText, { tuning: variant.tuning });
    plain.setAttribute("aria-label", asText.textContent);
  };
  const barOf = (i) => Math.floor(demo.notes[i][1] / perBar);
  playBar.addEventListener("click", () => chosen >= 0 && bar.range(config.times[barOf(chosen)], config.times[barOf(chosen) + 1]));
  const choose = (i, focus) => {
    if (i !== chosen) bar.stop();
    chosen = kept.chosen = i;
    playBar.disabled = false;
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
  const select = segmented(el.querySelector("[data-part]"), () => {
    delete kept.chosen;
    show();
  });
  const status = el.querySelector("[data-status]"), scroll = el.querySelector(".tabdemo-scroll");
  const playBar = el.querySelector("[data-bar-play]"), bar = player(playBar, el.dataset.audio, config, status);
  // Where each bar starts in the recording, from bar 1, and where the last one ends: made at build time.
  let chosenBar = 0;
  playBar.addEventListener("click", () => chosenBar && bar.range(config.times[chosenBar - 1], config.times[chosenBar]));
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
    const was = chosenBar;
    chosenBar = notes[i].bar;
    if (was !== chosenBar) bar.stop();
    playBar.disabled = false;
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
      const note = { g, text, svg, bar: part.notes[i][4] };
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
    chosenBar = 0;
    bar.stop();
    playBar.disabled = true;
  };
  // After a change of language it stands as it stood: the same part, the same note.
  const chosen = kept.chosen;
  if (kept.part) select.value = kept.part;
  show();
  if (chosen !== undefined && notes[chosen]) choose(chosen, false);
}

// The "How sure" cards: on a phone a row that scrolls, with "1 of 3" under it following the card in view; only
// there is the row a place of its own for the keyboard (on a wider screen the cards all stand in view).
const narrow = matchMedia("(max-width: 600px)");
function sureRow(row) {
  const count = row.nextElementSibling?.classList.contains("sure-count") ? row.nextElementSibling : null;
  const cards = [...row.children];
  const fit = () => {
    if (narrow.matches) {
      row.setAttribute("role", "region");
      row.tabIndex = 0;
    } else {
      row.removeAttribute("role");
      row.removeAttribute("tabindex");
    }
  };
  const show = () => {
    if (!count) return;
    const left = row.getBoundingClientRect().left;
    let at = 0, near = Infinity;
    cards.forEach((card, i) => {
      const far = Math.abs(card.getBoundingClientRect().left - left - parseFloat(getComputedStyle(row).paddingLeft));
      if (far < near) [at, near] = [i, far];
    });
    // (At the end of the row the last card is the one in view, though it cannot reach the row's start.)
    if (row.scrollLeft + row.clientWidth >= row.scrollWidth - 2) at = cards.length - 1;
    count.textContent = fill(row.dataset.count, { n: at + 1, total: cards.length });
  };
  narrow.addEventListener("change", fit);
  row.addEventListener("scroll", show, { passive: true });
  // (A page's own words may give the counter: they change with the language where they stand.)
  document.addEventListener("scribe:lang", show);
  fit();
  show();
  count?.classList.remove("await-js");
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
  within(root, ".sure-grid[data-count]").forEach(sureRow);
  // The table of where every app runs is folded on a phone, until the reader opens it.
  within(root, ".matrix-fold").forEach((fold) => {
    if (narrow.matches) fold.open = false;
  });
  within(root, "[data-stages]").forEach(stages);
  lazily("[data-tabdemo]", tabdemo);
  lazily("[data-partview]", partview);
}
enhance(document);
document.addEventListener("scribe:lang", (e) => e.detail.replaced.forEach(enhance));
