// What the front pages' figures do when a visitor touches them. Every figure is complete in the HTML;
// this adds the moving parts: the strip under the headline, the steps, the device table and the tab viewer.

const calm = matchMedia("(prefers-reduced-motion: reduce)");
const SVG = "http://www.w3.org/2000/svg";
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);
const make = (name, attributes = {}, parent) => {
  const el = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
  parent?.append(el);
  return el;
};

// The strip: sound on the right of the pen, written music on the left. --t is how far it has run, in px.
function strip(el) {
  const d = JSON.parse(el.dataset.strip);
  const stage = el.querySelector(".strip-stage");
  const range = el.querySelector("input[type=range]");
  const out = el.querySelector("output");
  const button = el.querySelector("[data-strip-play]");
  el.querySelector(".strip-controls").hidden = false;
  // `quiet` is the run it makes by itself when it comes into view: no sound, and the button still says Play.
  let t = 0, from = 0, started = 0, playing = false, quiet = false, frame = 0, audio = null, voices = [];

  const set = (seconds, byHand) => {
    t = Math.max(0, Math.min(d.dur, seconds));
    stage.style.setProperty("--t", (t * d.pps).toFixed(1));
    if (!byHand) range.value = t;
    const beat = Math.max(0, d.beats.findLastIndex((b) => b <= t));
    out.textContent = d.barBeat.replace("{bar}", Math.floor(beat / d.perBar) + 1).replace("{beat}", (beat % d.perBar) + 1);
    range.setAttribute("aria-valuetext", out.textContent);
  };
  const stop = () => {
    playing = quiet = false;
    cancelAnimationFrame(frame);
    for (const v of voices) try { v.stop(); } catch {}
    voices = [];
    button.textContent = d.play;
  };
  // The notes as the engine wrote them, as plucks: a way to hear the tab, not the take.
  const sound = () => {
    audio ??= new AudioContext();
    audio.resume();
    const now = audio.currentTime + 0.05;
    for (const [on, length, pitch] of d.notes) {
      if (on < t - 0.05) continue;
      const at = now + on - t, hold = Math.max(0.3, length);
      const gain = audio.createGain();
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.2, at + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + hold);
      gain.connect(audio.destination);
      // A low string is below what a phone's speaker gives: its octave sounds along.
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
    set(from + (now - started) / 1000);
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
      sound();
    }
    frame = requestAnimationFrame(run);
  };
  button.addEventListener("click", () => {
    if (playing && !quiet) return stop();
    // During the quiet run the button says Play, and Play it is: sound from where the strip is now.
    if (playing) stop();
    play(true);
  });
  range.addEventListener("input", () => {
    if (playing) stop();
    set(+range.value, true);
  });
  document.addEventListener("visibilitychange", () => document.hidden && playing && stop());

  // Once, when it comes into view, it writes itself out without sound. Not when motion is unwanted.
  set(calm.matches ? d.dur * 0.4 : 0);
  if (!calm.matches) {
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
  let current = 0;
  const show = (i) => {
    current = Math.max(0, Math.min(items.length - 1, i));
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
  // Every step takes the height of the tallest, so the buttons under them stay where they are.
  const settle = () => {
    list.style.minHeight = "";
    items.forEach((item) => (item.hidden = false));
    list.classList.remove("live");
    const tallest = Math.max(...items.map((item) => item.offsetHeight));
    list.classList.add("live");
    list.style.minHeight = `${tallest}px`;
    show(current);
  };
  list.setAttribute("aria-live", "polite");
  list.before(nav);
  list.after(foot);
  settle();
  let width = innerWidth;
  addEventListener("resize", () => width !== innerWidth && ((width = innerWidth), settle()));
  document.fonts?.ready.then(settle);
}

// The device table: choosing a device shows its row alone.
function matrix(el) {
  const pick = el.querySelector(".matrix-pick");
  const buttons = [...pick.querySelectorAll("button")];
  pick.hidden = false;
  for (const b of buttons) {
    b.addEventListener("click", () => {
      const on = b.getAttribute("aria-pressed") !== "true";
      buttons.forEach((x) => x.setAttribute("aria-pressed", String(x === b && on)));
      for (const row of el.querySelectorAll("tbody tr")) row.hidden = on && row.dataset.device !== b.dataset.device;
    });
  }
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
  el.querySelector(".tabdemo-controls").hidden = false;
  el.querySelector(".tabdemo-hint").hidden = false;
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
    const strings = variant.open.length, frets = Math.max(12, ...spots.map(([, f]) => f), place[1] ?? 0);
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
    svg.setAttribute("aria-label", fill(config.label, { title: demo.title, bars: config.bars, tuning: variant.tuning }));
    const summary = fill(lost > 1 ? w.summary_lost : lost ? w.summary_lost_one : w.summary,
      { tuning: variant.tuning, capo: capo ? capo.selectedOptions[0].textContent.toLowerCase() : config.noCapo, lost })
      + (left ? " " + fill(w.summary_left, { left }) : "");
    status.textContent = chosen < 0 ? summary : describe(chosen);
    if (chosen >= 0) drawNeck(chosen);
  };
  const choose = (i, focus) => {
    chosen = i;
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
  draw();
}

const start = (selector, enhance) => document.querySelectorAll(selector).forEach((el) => enhance(el));
// A viewer's data is fetched when it is about to be seen.
const lazily = (selector, enhance) => start(selector, (el) => {
  const near = new IntersectionObserver((entries) => {
    if (!entries[0].isIntersecting) return;
    near.disconnect();
    enhance(el).catch(() => {});
  }, { rootMargin: "600px" });
  near.observe(el);
});
start("[data-strip]", strip);
start("[data-stages]", stages);
start("[data-matrix]", matrix);
lazily("[data-tabdemo]", tabdemo);
