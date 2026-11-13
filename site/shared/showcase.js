// What the front pages' figures do when a visitor touches them. Every figure is complete in the HTML;
// this adds the moving parts: the strip under the headline, the steps, the device table and the tab viewer.

const calm = matchMedia("(prefers-reduced-motion: reduce)");

// The strip: sound on the right of the pen, written music on the left. --t is how far it has run, in px.
function strip(el) {
  const d = JSON.parse(el.dataset.strip);
  const stage = el.querySelector(".strip-stage");
  const range = el.querySelector("input[type=range]");
  const out = el.querySelector("output");
  const button = el.querySelector("[data-strip-play]");
  el.querySelector(".strip-controls").hidden = false;
  let t = 0, from = 0, started = 0, playing = false, frame = 0, audio = null, voices = [];

  const set = (seconds, byHand) => {
    t = Math.max(0, Math.min(d.dur, seconds));
    stage.style.setProperty("--t", (t * d.pps).toFixed(1));
    if (!byHand) range.value = t;
    const beat = Math.max(0, d.beats.findLastIndex((b) => b <= t));
    out.textContent = d.barBeat.replace("{bar}", Math.floor(beat / d.perBar) + 1).replace("{beat}", (beat % d.perBar) + 1);
    range.setAttribute("aria-valuetext", out.textContent);
  };
  const silence = () => {
    for (const v of voices) try { v.stop(); } catch {}
    voices = [];
  };
  const stop = () => {
    playing = false;
    cancelAnimationFrame(frame);
    silence();
    button.textContent = d.play;
  };
  // The notes as the engine wrote them, as plucks: a way to hear the tab, not the recording.
  const sound = () => {
    audio ??= new AudioContext();
    audio.resume();
    const now = audio.currentTime + 0.05;
    for (const [on, length, pitch] of d.notes) {
      if (on < t - 0.05) continue;
      const at = now + on - t, hold = Math.max(0.3, length);
      const gain = audio.createGain();
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.22, at + 0.012);
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
    from = t;
    started = performance.now();
    button.textContent = d.pause;
    if (withSound) sound();
    frame = requestAnimationFrame(run);
  };
  button.addEventListener("click", () => (playing ? stop() : play(true)));
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

// The steps: one at a time, with a button for each and for the one before and after.
function stages(list) {
  const items = [...list.children];
  const nav = document.createElement("div");
  nav.className = "stages-nav";
  const buttons = items.map((item, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<span>${i + 1}</span> ${item.querySelector("h3").textContent}`;
    b.addEventListener("click", () => show(i));
    nav.append(b);
    return b;
  });
  const step = (label, by) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button outline";
    b.textContent = label;
    b.addEventListener("click", () => show(current + by));
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
    buttons.forEach((b, k) => (k === current ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current")));
    previous.disabled = current === 0;
    next.disabled = current === items.length - 1;
  };
  list.classList.add("live");
  list.setAttribute("aria-live", "polite");
  list.before(nav);
  list.after(foot);
  show(0);
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

// The tab viewer: the same notes in another tuning or with a capo, as the core's solver placed them.
async function tabdemo(el) {
  const config = JSON.parse(el.dataset.tabdemo), w = config.words;
  const demo = await (await fetch(el.dataset.src)).json();
  const tuning = el.querySelector("[data-tuning]"), capo = el.querySelector("[data-capo]");
  const status = el.querySelector("[data-status]");
  const notes = [...el.querySelectorAll("g.note")];
  const x = notes.map((g) => g.getAttribute("transform").match(/translate\(([\d.]+)/)[1]);
  const perBeat = demo.ticks_per_beat, perBar = demo.meter.beats * perBeat;
  let variant = demo.variants[demo.default], chosen = -1;
  el.querySelector(".tabdemo-controls").hidden = false;
  el.querySelector(".tabdemo-hint").hidden = false;

  const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);
  const where = (string, fret) => fill(w.place, { string: w.ordinals[string - 1], fret });
  const describe = (i) => {
    const [pitch, start] = demo.notes[i], place = variant.places[i];
    const at = fill(w.at, { bar: Math.floor(start / perBar) + 1, beat: Math.floor((start % perBar) / perBeat) + 1, name: w.names[pitch % 12] });
    if (place[2]) return `${at} ${w.lost}`;
    const others = [];
    for (let k = 3; k < place.length; k += 2) others.push(where(place[k], place[k + 1]));
    const doubt = demo.notes[i][3] ? ` ${w.doubt}` : "";
    return `${at} ${where(place[0], place[1])}.${doubt} ${others.length ? fill(w.also, { places: others.join(w.or) }) : w.only}`;
  };
  const draw = () => {
    variant = demo.variants[`${tuning.value}/${capo.value}`];
    let lost = 0;
    notes.forEach((g, i) => {
      const [string, fret, gone] = variant.places[i];
      lost += gone;
      g.setAttribute("transform", `translate(${x[i]} ${gone ? config.top - 30 : config.top + config.gap * (string - 1)})`);
      g.classList.toggle("lost", !!gone);
      g.querySelector("text").textContent = gone ? "!" : fret;
      g.setAttribute("aria-label", describe(i));
    });
    const summary = fill(lost > 1 ? w.summary_lost : lost ? w.summary_lost_one : w.summary, { tuning: variant.tuning, capo: capo.selectedOptions[0].textContent.toLowerCase(), lost });
    status.textContent = chosen < 0 ? summary : `${summary} ${describe(chosen)}`;
  };
  const choose = (i, focus) => {
    chosen = i;
    notes.forEach((g, k) => {
      g.classList.toggle("chosen", k === i);
      g.tabIndex = k === i ? 0 : -1;
    });
    if (focus) notes[i].focus();
    draw();
  };
  notes.forEach((g, i) => {
    g.setAttribute("role", "button");
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
  const svg = el.querySelector("svg");
  svg.setAttribute("role", "group");
  tuning.addEventListener("change", draw);
  capo.addEventListener("change", draw);
  draw();
}

const start = (selector, make) => document.querySelectorAll(selector).forEach((el) => make(el));
start("[data-strip]", strip);
start("[data-stages]", stages);
start("[data-matrix]", matrix);
start("[data-tabdemo]", (el) => {
  // Its data is fetched when the viewer is about to be seen.
  const near = new IntersectionObserver((entries) => {
    if (!entries[0].isIntersecting) return;
    near.disconnect();
    tabdemo(el).catch(() => {});
  }, { rootMargin: "600px" });
  near.observe(el);
});
