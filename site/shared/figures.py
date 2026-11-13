"""Figures the pages ask for with {{figure <name> …}}: drawn at build time from files in the repository
(the apps' fixtures, eval/baselines.json), so what a page shows is what the engine answered.

Each figure is complete without JavaScript; site/shared/showcase.js makes it something to play with.
A product's own figures live in site/<product>/figures.py, with the same shape: name(page, **args) -> HTML.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORDS = {
    "en": {
        "play": "Play", "pause": "Pause", "position": "Position in the recording", "bar_beat": "Bar {bar}, beat {beat}",
        "strip_label": "A recording of {title} on the right turns into tab on the left as it passes the pen: {notes} notes in {bars} bars, {doubt} marked with a question mark.",
        "strip_note": "{title}: a made-up line, played by a synthesizer and written down by the engine. Play gives you the notes it wrote, not a recording.",
        "stage": "Step {n} of {total}", "previous": "Previous step", "next": "Next step", "engine_stage": "In the engine: {name}",
        "tuning": "Tuning", "capo": "Capo", "no_capo": "No capo", "capo_n": "Capo on fret {n}",
        "tab_label": "Tab of {title}, {bars} bars, in {tuning}.", "tab_scroll": "The tab. Scroll sideways to read on.",
        "pick": "Choose a number in the tab to see where else that note can be played. The arrow keys move from note to note.",
        "as_text": "The same tab as text",
        "of_100": "{n} of 100",
        "platform": "Device", "status": "Status", "alone": "Works by itself", "with_bandroom": "Needs Bandroom on your computer",
        "which_device": "Which device do you have?",
    },
    "nb": {
        "play": "Spill", "pause": "Pause", "position": "Posisjon i opptaket", "bar_beat": "Takt {bar}, slag {beat}",
        "strip_label": "Et opptak av {title} til høyre blir til tab til venstre når det passerer pennen: {notes} toner i {bars} takter, {doubt} merket med spørsmålstegn.",
        "strip_note": "{title}: en oppdiktet linje, spilt av en synthesizer og skrevet ned av motoren. Spill gir deg tonene den skrev, ikke et opptak.",
        "stage": "Steg {n} av {total}", "previous": "Forrige steg", "next": "Neste steg", "engine_stage": "I motoren: {name}",
        "tuning": "Stemming", "capo": "Capo", "no_capo": "Uten capo", "capo_n": "Capo på bånd {n}",
        "tab_label": "Tab av {title}, {bars} takter, i {tuning}.", "tab_scroll": "Tabben. Rull sidelengs for å lese videre.",
        "pick": "Velg et tall i tabben for å se hvor ellers den tonen kan spilles. Piltastene går fra tone til tone.",
        "as_text": "Den samme tabben som tekst",
        "of_100": "{n} av 100",
        "platform": "Enhet", "status": "Status", "alone": "Virker alene", "with_bandroom": "Trenger Bandroom på datamaskinen",
        "which_device": "Hvilken enhet har du?",
    },
}


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def lookup(file: str, path: str) -> object:
    """A value in a JSON file of the repository: lookup("eval/baselines.json", "targets/fretted/suites/…")."""
    node = json.loads((ROOT / file).read_text())
    for key in path.split("/"):
        node = node[int(key)] if isinstance(node, list) else node[key]
    return node


class Take:
    """What the engine answered for a tab job, as the fixtures keep it (apps/fixtures/<name>)."""

    def __init__(self, fixture: str):
        folder = ROOT / fixture
        self.tab = json.loads((folder / "tab.json").read_text())
        self.job = json.loads((folder / "job.json").read_text())
        composition = json.loads((folder / "composition.json").read_text())
        self.title = self.job["title"]
        self.beats = composition["beat_times"]
        self.per_bar = self.tab["meter"]["beats"]
        self.notes = self.tab["notes"]
        self.strings = len(self.tab["instrument"]["tuning"]["strings"])
        self.end = max(n["offset_s"] for n in self.notes)
        xml = (folder / "tab.musicxml").read_text()
        # The engine draws a note it doubts in the doubt colour; each <note> carries <?fretted-note N?>.
        self.doubt = set()
        for note in re.findall(r"<note\b[^>]*>.*?</note>", xml, re.S):
            n = re.search(r"<\?fretted-note (\d+)\?>", note)
            if n and re.match(r'<note\b[^>]*color="#9A5200"', note):
                self.doubt.add(int(n.group(1)))
        self.bars = [self.beats[i] for i in range(0, len(self.beats), self.per_bar)]

    def tick_time(self, tick: float) -> float:
        """The second a tick of the written score falls on, from the beats the engine found."""
        beat = tick / self.tab["ticks_per_beat"]
        i = min(int(beat), len(self.beats) - 2)
        return self.beats[i] + (beat - i) * (self.beats[i + 1] - self.beats[i])

    def level(self, t: float) -> float:
        """How loud the take is at a second: each note a pluck that dies away. A drawing of the sound, not a measurement."""
        total = sum(math.exp(-(t - n["onset_s"]) / 0.3) for n in self.notes if n["onset_s"] <= t < n["offset_s"] + 0.1)
        wobble = 0.75 + 0.25 * math.sin(t * 91.7) * math.sin(t * 37.3)
        return min(1.0, total) * wobble


def wave_path(take: Take, x0: float, pps: float, mid: float, height: float, start: float = 0.0, end: float | None = None, step: float = 3.0) -> str:
    end = take.end + 0.4 if end is None else end
    parts, x = [], x0
    while (t := start + (x - x0) / pps) <= end:
        a = max(1.0, take.level(t) * height / 2)
        parts.append(f"M{number(x)} {number(mid - a)}V{number(mid + a)}")
        x += step
    return "".join(parts)


def tab_marks(take: Take, xs: list[float], top: float, gap: float, size: float = 15) -> tuple[str, float]:
    """The lines, fret numbers and marks of a tab, each note at its x."""
    out = []
    bottom = top + gap * (take.strings - 1)
    for s in range(take.strings):
        y = number(top + gap * s)
        out.append(f'<path class="string" d="M0 {y}H{number(max(xs) + 60)}"/>')
    for i, (n, x) in enumerate(zip(take.notes, xs)):
        doubt = " doubt" if i in take.doubt else ""
        if n["out_of_range"]:
            out.append(f'<g class="no-place"><rect x="{number(x - 8)}" y="{number(top - 40)}" width="16" height="18" rx="2"/>'
                       f'<text x="{number(x)}" y="{number(top - 26)}">!</text></g>')
            continue
        y = top + gap * (n["string"] - 1)
        wide = 7 if n["fret"] < 10 else 12
        out.append(f'<rect class="knock" x="{number(x - wide)}" y="{number(y - 8)}" width="{wide * 2}" height="16"/>'
                   f'<text class="fret{doubt}" x="{number(x)}" y="{number(y + size * 0.36)}" font-size="{size}">{n["fret"]}</text>')
        if doubt:
            out.append(f'<text class="mark" x="{number(x)}" y="{number(top - 24)}">?</text>')
    return "".join(out), bottom


def strip(page, fixture: str) -> str:
    """The hero: the take as sound on the right of a pen and as tab on the left; the page moves it."""
    w, take = WORDS[page.lang], Take(fixture)
    pps, x0, height, top, gap = 64.0, 0.0, 232, 104, 26
    width = math.ceil((take.end + 0.6) * pps)
    xs = [x0 + n["onset_s"] * pps for n in take.notes]
    marks, bottom = tab_marks(take, xs, top, gap, 17)
    bars = "".join(f'<path class="bar" d="M{number(x0 + t * pps - 14)} {top}V{bottom}"/>'
                   f'<text class="bar-no" x="{number(x0 + t * pps - 9)}" y="{top - 52}">{i + 1}</text>' for i, t in enumerate(take.bars))
    wave = wave_path(take, x0, pps, (top + bottom) / 2, 150)
    label = w["strip_label"].format(title=take.title, notes=len(take.notes), bars=len(take.bars), doubt=len(take.doubt))
    data = {"dur": round(take.end + 0.3, 2), "pps": pps, "beats": take.beats, "perBar": take.per_bar,
            "notes": [[round(n["onset_s"], 3), round(n["offset_s"] - n["onset_s"], 3), n["pitch"]] for n in take.notes],
            "barBeat": w["bar_beat"], "play": w["play"], "pause": w["pause"]}
    return f"""<figure class="strip" data-strip="{esc(json.dumps(data, separators=(",", ":")))}">
  <div class="strip-stage" role="img" aria-label="{esc(label)}">
    <div class="strip-ink"><svg class="tab-ink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false">{bars}{marks}</svg></div>
    <div class="strip-sound"><svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false"><path class="wave" d="{wave}"/></svg></div>
    <div class="strip-pen" aria-hidden="true"></div>
  </div>
  <div class="strip-controls" hidden>
    <button type="button" class="button outline" data-strip-play>{w["play"]}</button>
    <label class="strip-range"><span class="vh">{w["position"]}</span><input type="range" min="0" max="{round(take.end + 0.3, 2)}" step="0.05" value="0"></label>
    <output aria-live="off">{w["bar_beat"].format(bar=1, beat=1)}</output>
  </div>
  <figcaption>{w["strip_note"].format(title=esc(take.title))}</figcaption>
</figure>"""


def stages(page, fixture: str, seconds: str = "6.2") -> str:
    """The steps from sound to tab, each with what the engine had at that point for the take's first bars."""
    w, take, t = WORDS[page.lang], Take(fixture), page.product.data[page.lang]["stages"]
    end = float(seconds)
    width, height, x0 = 360, 190, 14
    pps = (width - 2 * x0) / end
    notes = [(i, n) for i, n in enumerate(take.notes) if n["onset_s"] < end]
    mid = 100
    wave = wave_path(take, x0, pps, mid, 120, 0.0, end, 2.5)
    beats = "".join(f'<path class="beat{" down" if i % take.per_bar == 0 else ""}" d="M{number(x0 + b * pps)} 22V{height - 20}"/>'
                    for i, b in enumerate(take.beats) if b < end)
    bar_numbers = "".join(f'<text class="bar-no" x="{number(x0 + b * pps + 3)}" y="16">{i + 1}</text>' for i, b in enumerate(take.bars) if b < end)
    low, high = min(n["pitch"] for _, n in notes), max(n["pitch"] for _, n in notes)
    row = (height - 60) / (high - low + 1)

    def roll(written: bool) -> str:
        out = []
        for i, n in notes:
            if written:
                a, b = take.tick_time(n["start"]), take.tick_time(n["start"] + n["dur"])
            else:
                a, b = n["onset_s"], n["offset_s"]
            y = 30 + (high - n["pitch"]) * row
            out.append(f'<rect class="heard{" doubt" if i in take.doubt else ""}" x="{number(x0 + a * pps)}" y="{number(y)}" '
                       f'width="{number(max(3, (min(b, end) - a) * pps - 1.5))}" height="{number(row - 1.5)}" rx="2" opacity="{number(0.35 + 0.65 * n["confidence"])}"/>')
        return "".join(out)

    sub = Take(fixture)
    sub.notes = [n for _, n in notes]
    sub.doubt = {k for k, (i, _) in enumerate(notes) if i in take.doubt}
    marks, bottom = tab_marks(sub, [x0 + take.tick_time(n["start"]) * pps for n in sub.notes], 62, 26, 15)
    bar_lines = "".join(f'<path class="bar" d="M{number(x0 + b * pps - 6)} 62V{bottom}"/>' for b in take.bars if b < end)
    faint_beats = beats.replace('class="beat', 'class="beat faint')
    frames = [("", f'<path class="wave" d="{wave}"/>'),
              ("beats", f'<path class="wave faint" d="{wave}"/>{beats}{bar_numbers}'),
              ("transcribe", f"{faint_beats}{roll(False)}"),
              ("notes", f"{beats}{bar_numbers}{roll(True)}"),
              ("arrange", f"{bar_lines}{bar_numbers}{marks}")]
    names = {s["kind"]: s["name"] for s in reversed(take.job["stages"])}
    facts = {"tempo": number(take.tab["tempo_bpm"]), "beats": take.per_bar, "unit": take.tab["meter"]["beat_unit"],
             "notes": len(take.notes), "doubt": len(take.doubt), "key": take.tab["key"]["name"],
             "open": next((s["open_notes"] for s in take.tab["tuning_suggestions"] if s["preset"] == take.tab["preset"]), 0),
             "tuning": take.tab["instrument"]["tuning"]["name"]}
    items = []
    for n, ((kind, body), text) in enumerate(zip(frames, t), 1):
        engine = f'<span class="stage-engine">{w["engine_stage"].format(name=f"<code>{esc(names[kind])}</code>")}</span>' if kind in names else ""
        items.append(f"""  <li class="stage">
    <div class="stage-text">
      <p class="stage-count">{w["stage"].format(n=n, total=len(frames))}</p>
      <h3>{text["title"]}</h3>
      <p>{text["text"].format(**facts)}</p>
      {engine}
    </div>
    <svg class="stage-figure tab-ink" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(text["alt"].format(**facts))}">{body}</svg>
  </li>""")
    return (f'<ol class="stages" data-stages data-previous="{w["previous"]}" data-next="{w["next"]}">\n' + "\n".join(items) + "\n</ol>")


def tabdemo(page, data: str, fixture: str) -> str:
    """The tab viewer: the engine's tab of a take, drawn so the page can show another tuning or capo of the same notes."""
    w = WORDS[page.lang]
    demo = json.loads((ROOT / data).read_text())
    variant = demo["variants"][demo["default"]]
    per_bar = demo["meter"]["beats"] * demo["ticks_per_beat"]
    k, x0, top, gap = 1.9, 34, 64, 22
    strings = len(variant["open"])
    last = max(n[1] + n[2] for n in demo["notes"])
    bars = math.ceil(last / per_bar)
    width, bottom = math.ceil(x0 + bars * per_bar * k + 16), top + gap * (strings - 1)
    out = [f'<path class="string" d="M10 {top + gap * s}H{width - 10}"/>' for s in range(strings)]
    for b in range(bars + 1):
        x = number(x0 + b * per_bar * k - 12)
        out.append(f'<path class="bar" d="M{x} {top}V{bottom}"/>')
        if b < bars:
            out.append(f'<text class="bar-no" x="{number(x0 + b * per_bar * k - 8)}" y="{top - 40}">{b + 1}</text>')
    for i, (note, place) in enumerate(zip(demo["notes"], variant["places"])):
        x = number(x0 + note[1] * k)
        lost = place[2]
        y = top - 30 if lost else top + gap * (place[0] - 1)
        classes = "note" + (" doubt" if note[3] else "") + (" lost" if lost else "")
        out.append(f'<g class="{classes}" data-i="{i}" transform="translate({x} {y})"><rect class="knock" x="-9" y="-9" width="18" height="18" rx="3"/>'
                   f'<text class="fret" y="5.5">{"!" if lost else place[1]}</text></g>')
        if note[3]:
            out.append(f'<text class="mark" x="{x}" y="{top - 14}">?</text>')
    tunings = "".join(f'<option value="{p}"{" selected" if demo["default"].startswith(p + "/") else ""}>{esc(demo["variants"][p + "/0"]["tuning"])}</option>'
                      for p in demo["presets"])
    capos = "".join(f'<option value="{c}">{w["no_capo"] if c == 0 else w["capo_n"].format(n=c)}</option>' for c in demo["capos"])
    label = w["tab_label"].format(title=demo["title"], bars=bars, tuning=variant["tuning"])
    text_tab = esc((ROOT / fixture / "tab.txt").read_text().rstrip())
    words = page.product.data[page.lang]["tabdemo"]
    config = {"top": top, "gap": gap, "words": words}
    return f"""<div class="tabdemo" data-src="@/assets/data/{Path(data).name}" data-tabdemo="{esc(json.dumps(config, separators=(",", ":"), ensure_ascii=False))}">
  <div class="tabdemo-controls" hidden>
    <label>{w["tuning"]} <select data-tuning>{tunings}</select></label>
    <label><span class="vh">{w["capo"]}</span> <select data-capo>{capos}</select></label>
  </div>
  <div class="tabdemo-scroll" role="region" aria-label="{esc(w["tab_scroll"])}" tabindex="0">
    <svg class="tab-ink" width="{width}" height="{bottom + 22}" viewBox="0 0 {width} {bottom + 22}" role="img" aria-label="{esc(label)}">{"".join(out)}</svg>
  </div>
  <p class="tabdemo-status" data-status role="status">{words["start"]}</p>
  <p class="tabdemo-hint" hidden>{w["pick"]}</p>
  <details><summary>{w["as_text"]}</summary><pre>{text_tab}</pre></details>
</div>"""


def dots(page, path: str, file: str = "eval/baselines.json", kind: str = "") -> str:
    """A hundred squares with a share of them filled: a measured rate from a data file, as so many of 100."""
    n = round(float(lookup(file, path)) * 100)
    cells = "".join(f'<rect class="{"on" if i < n else "off"}" x="{(i % 10) * 12}" y="{(i // 10) * 12}" width="10" height="10" rx="2"/>' for i in range(100))
    return (f'<svg class="dots {kind}" viewBox="0 0 118 118" role="img" aria-label="{WORDS[page.lang]["of_100"].format(n=n)}">{cells}</svg>')


def platforms(page) -> str:
    """What each device can do by itself and what it needs the computer for, from the product's [[platforms]]."""
    w, rows = WORDS[page.lang], page.product.data["platforms"]
    lang = page.lang
    chips = "".join(f'<button type="button" data-device="{r["id"]}" aria-pressed="false">{r[lang]["name"]}</button>' for r in rows)
    body = "".join(f'\n      <tr data-device="{r["id"]}"><th scope="row">{r[lang]["name"]}<span class="status">{r[lang]["status"]}</span></th>'
                   f'<td data-label="{w["alone"]}">{r[lang]["alone"]}</td><td data-label="{w["with_bandroom"]}">{r[lang]["bandroom"]}</td></tr>' for r in rows)
    return f"""<div class="matrix" data-matrix>
  <div class="matrix-pick" role="group" aria-label="{w["which_device"]}" hidden>{chips}</div>
  <div class="table-scroll" role="region" aria-labelledby="matrix-caption-{page.product.id}" tabindex="0">
    <table>
      <caption id="matrix-caption-{page.product.id}" class="vh">{page.product.data[lang]["name"]}</caption>
      <thead><tr><th scope="col">{w["platform"]}</th><th scope="col">{w["alone"]}</th><th scope="col">{w["with_bandroom"]}</th></tr></thead>
      <tbody>{body}
      </tbody>
    </table>
  </div>
</div>"""
