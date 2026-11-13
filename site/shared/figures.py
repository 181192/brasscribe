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
        "strip_label": "The take of {title} as a sound wave on the right turns into tab on the left as it passes the pen: {notes} notes in {bars} bars, {doubt} marked with a question mark and {lost} with no place on the neck.",
        "strip_note": "{title}: a made-up line, played by a synthesizer. The sound wave is that take's loudness; the tab, its question mark and its {lost} notes with no place are what the engine answered. Play sounds the notes it wrote, not the take.",
        "stage": "Step {n} of {total}", "previous": "Previous step", "next": "Next step", "steps": "Steps", "engine_stage": "In the engine: {name}",
        "tuning": "Tuning", "capo": "Capo", "no_capo": "No capo", "capo_n": "Capo on fret {n}",
        "tab_label": "Tab of {title}, {bars} bars, in {tuning}.", "tab_scroll": "The tab. Scroll sideways to read on.",
        "pick": "Choose a number in the tab to see where else that note can be played. The arrow keys move from note to note.",
        "as_text": "The tab as text, as the engine wrote it ({tuning})",
        "of_100": "{n} of 100",
        "platform": "Device", "status": "Status", "table": "What {name} does on each device", "alone": "Works by itself", "with_bandroom": "Needs Bandroom on your computer",
        "which_device": "Which device do you have?",
    },
    "nb": {
        "play": "Spill", "pause": "Pause", "position": "Posisjon i opptaket", "bar_beat": "Takt {bar}, slag {beat}",
        "strip_label": "Opptaket av {title} som lydbølge til høyre blir til tab til venstre når det passerer pennen: {notes} toner i {bars} takter, {doubt} merket med spørsmålstegn og {lost} uten plass på halsen.",
        "strip_note": "{title}: en oppdiktet linje, spilt av en synthesizer. Lydbølgen er lydstyrken i det opptaket; tabben, spørsmålstegnet og de {lost} tonene uten plass er det motoren svarte. Spill gir deg tonene den skrev, ikke opptaket.",
        "stage": "Steg {n} av {total}", "previous": "Forrige steg", "next": "Neste steg", "steps": "Steg", "engine_stage": "I motoren: {name}",
        "tuning": "Stemming", "capo": "Capo", "no_capo": "Uten capo", "capo_n": "Capo på bånd {n}",
        "tab_label": "Tab av {title}, {bars} takter, i {tuning}.", "tab_scroll": "Tabben. Rull sidelengs for å lese videre.",
        "pick": "Velg et tall i tabben for å se hvor ellers den tonen kan spilles. Piltastene går fra tone til tone.",
        "as_text": "Tabben som tekst, slik motoren skrev den ({tuning})",
        "of_100": "{n} av 100",
        "platform": "Enhet", "status": "Status", "table": "Dette gjør {name} på hver enhet", "alone": "Virker alene", "with_bandroom": "Trenger Bandroom på datamaskinen",
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


def doubt_colour() -> str:
    """The colour the core draws a doubtful note in: the one place that says which notes carry a "?"."""
    return re.search(r'DOUBT_COLOR: &str = "(#[0-9A-Fa-f]{6})"', (ROOT / "core" / "targets" / "fretted" / "src" / "tab.rs").read_text()).group(1)


def doubtful(musicxml: str) -> set[int]:
    """The notes the engine drew as doubtful: each <note> of a tab carries <?fretted-note N?>."""
    colour, marked = doubt_colour(), set()
    for note in re.findall(r"<note\b[^>]*>.*?</note>", musicxml, re.S):
        n = re.search(r"<\?fretted-note (\d+)\?>", note)
        if n and re.match(rf'<note\b[^>]*color="{colour}"', note):
            marked.add(int(n.group(1)))
    return marked


def key_name(key: dict, lang: str) -> str:
    """A key as it is said: "Em" is E minor, e-moll."""
    root = key["name"][:-1] if key["mode"] == "minor" else key["name"]
    if lang == "en":
        return f'{root.replace("#", " sharp").replace("b", " flat") if len(root) > 1 else root} {key["mode"]}'
    letter = {"B": "H", "Bb": "B"}.get(root, root[0] + {"#": "iss", "b": "ess"}.get(root[1:], ""))
    return f"{letter.lower()}-moll" if key["mode"] == "minor" else f"{letter}-dur"


class Take:
    """What the engine answered for a tab job, as the fixtures keep it (apps/fixtures/<name>), and the loudness of
    the audio it was given (made from that audio by the product's make_demo.py)."""

    def __init__(self, fixture: str, sound: str = ""):
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
        self.doubt = doubtful((folder / "tab.musicxml").read_text())
        self.lost = [i for i, n in enumerate(self.notes) if n["out_of_range"]]
        self.bars = [self.beats[i] for i in range(0, len(self.beats), self.per_bar)]
        heard = json.loads((ROOT / sound).read_text()) if sound else None
        self.peaks, self.rate = (heard["peak"], heard["per_second"]) if heard else ([], 1)

    def tick_time(self, tick: float) -> float:
        """The second a tick of the written score falls on, from the beats the engine found."""
        beat = tick / self.tab["ticks_per_beat"]
        i = min(int(beat), len(self.beats) - 2)
        return self.beats[i] + (beat - i) * (self.beats[i + 1] - self.beats[i])

    def level(self, t: float, width: float) -> float:
        """How loud the take is from a second on, for `width` seconds: the highest peak there."""
        a, b = int(t * self.rate), max(int(t * self.rate) + 1, int((t + width) * self.rate))
        return max(self.peaks[a:b], default=0.0)

    def facts(self, lang: str) -> dict:
        own = next((s for s in self.tab["tuning_suggestions"] if s["preset"] == self.tab["preset"]), {})
        return {"title": self.title, "tempo": round(self.tab["tempo_bpm"]), "beats": self.per_bar, "unit": self.tab["meter"]["beat_unit"],
                "notes": len(self.notes), "doubt": len(self.doubt), "lost": len(self.lost), "key": key_name(self.tab["key"], lang),
                "open": own.get("open_notes", 0), "tuning": self.tab["instrument"]["tuning"]["name"], "strings": self.strings,
                "bars": len(self.bars)}


def wave_path(take, x0: float, pps: float, mid: float, height: float, start: float = 0.0, end: float | None = None, step: float = 3.0) -> str:
    end = take.end + 0.4 if end is None else end
    parts, x = [], x0
    while (t := start + (x - x0) / pps) <= end:
        a = max(0.8, take.level(t, step / pps) * height / 2)
        parts.append(f"M{number(x)} {number(mid - a)}V{number(mid + a)}")
        x += step
    return "".join(parts)


def tab_marks(take: Take, xs: list[float], top: float, gap: float, size: float = 15, only: list[int] | None = None) -> tuple[str, float]:
    """The lines, fret numbers and marks of a tab, each note at its x: a "?" over the lines for a doubtful note,
    a boxed "!" under them for one with no place on the neck."""
    out = []
    bottom = top + gap * (take.strings - 1)
    for s in range(take.strings):
        out.append(f'<path class="string" d="M0 {number(top + gap * s)}H{number(max(xs) + 60)}"/>')
    for i, x in zip(only if only is not None else range(len(take.notes)), xs):
        n = take.notes[i]
        if n["string"] is None:
            if n["out_of_range"]:
                out.append(f'<g class="no-place"><rect x="{number(x - 9)}" y="{number(bottom + 10)}" width="18" height="18" rx="2"/>'
                           f'<text x="{number(x)}" y="{number(bottom + 24)}">!</text></g>')
            continue
        y = top + gap * (n["string"] - 1)
        wide = 6 if n["fret"] < 10 else 11
        doubt = " doubt" if i in take.doubt else ""
        out.append(f'<rect class="knock" x="{number(x - wide)}" y="{number(y - 8)}" width="{wide * 2}" height="16"/>'
                   f'<text class="fret{doubt}" x="{number(x)}" y="{number(y + size * 0.36)}" font-size="{size}">{n["fret"]}</text>')
        if doubt:
            out.append(f'<text class="mark" x="{number(x)}" y="{number(top - 12)}">?</text>')
    return "".join(out), bottom


def strip(page, fixture: str, sound: str) -> str:
    """The hero: the take as sound on the right of a pen and as tab on the left; the page moves it."""
    w, take = WORDS[page.lang], Take(fixture, sound)
    pps, top, gap = 60.0, 64, 22
    width = math.ceil((take.end + 0.6) * pps)
    xs = [n["onset_s"] * pps for n in take.notes]
    marks, bottom = tab_marks(take, xs, top, gap, 16)
    height = bottom + 44
    bars = "".join(f'<path class="bar" d="M{number(t * pps - 16)} {top}V{bottom}"/>'
                   f'<text class="bar-no" x="{number(t * pps - 12)}" y="{top - 34}">{i + 1}</text>' for i, t in enumerate(take.bars))
    wave = wave_path(take, 0.0, pps, (top + bottom) / 2, bottom - top + 40)
    facts = take.facts(page.lang)
    data = {"dur": round(take.end + 0.3, 2), "pps": pps, "beats": take.beats, "perBar": take.per_bar,
            "notes": [[round(n["onset_s"], 3), round(n["offset_s"] - n["onset_s"], 3), n["pitch"]] for n in take.notes if not n["out_of_range"]],
            "barBeat": w["bar_beat"], "play": w["play"], "pause": w["pause"]}
    return f"""<figure class="strip" data-strip="{esc(json.dumps(data, separators=(",", ":")))}" style="--strip-height: {height}px">
  <div class="strip-stage" role="img" aria-label="{esc(w["strip_label"].format(**facts))}">
    <div class="strip-ink"><svg class="tab-ink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false">{bars}{marks}</svg></div>
    <div class="strip-sound"><svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false"><path class="wave" d="{wave}"/></svg></div>
    <div class="strip-pen" aria-hidden="true"></div>
  </div>
  <div class="strip-controls" hidden>
    <button type="button" class="button outline" data-strip-play>{w["play"]}</button>
    <label class="strip-range"><span class="vh">{w["position"]}</span><input type="range" min="0" max="{round(take.end + 0.3, 2)}" step="0.25" value="0"></label>
    <output aria-live="off">{w["bar_beat"].format(bar=1, beat=1)}</output>
  </div>
  <figcaption>{w["strip_note"].format(**facts)}</figcaption>
</figure>"""


def stages(page, fixture: str, sound: str, bars: str = "2") -> str:
    """The steps from sound to tab, each with what the engine had at that point for the take's first bars."""
    w, take, t = WORDS[page.lang], Take(fixture, sound), page.product.data[page.lang]["stages"]
    end = take.bars[int(bars)]
    width, height, x0 = 360, 200, 18
    pps = (width - 2 * x0) / end
    shown = [i for i, n in enumerate(take.notes) if n["onset_s"] < end - 0.05]
    wave = wave_path(take, x0, pps, 104, 150, 0.0, end, 2.0)
    beat_lines = [(i, b) for i, b in enumerate(take.beats) if b <= end + 0.01]
    beats = "".join(f'<path class="beat{" down" if i % take.per_bar == 0 else ""}" d="M{number(x0 + b * pps)} 24V{height - 14}"/>' for i, b in beat_lines)
    faint_beats = beats.replace('class="beat', 'class="beat faint')
    bar_numbers = "".join(f'<text class="bar-no" x="{number(x0 + b * pps + 3)}" y="16">{i // take.per_bar + 1}</text>'
                          for i, b in beat_lines if i % take.per_bar == 0 and b < end - 0.1)
    low, high = min(take.notes[i]["pitch"] for i in shown), max(take.notes[i]["pitch"] for i in shown if not take.notes[i]["out_of_range"])
    row = (height - 50) / (high - low + 1)

    def block(i: int, written: bool, kind: str) -> str:
        n = take.notes[i]
        a, b = (take.tick_time(n["start"]), take.tick_time(n["start"] + n["dur"])) if written else (n["onset_s"], n["offset_s"])
        y = 28 + (high - min(n["pitch"], high)) * row
        # A note is its start, a block, and how long it rang, a thin line after it.
        x, tall, long = x0 + a * pps, max(3.0, row - 1.0), max(0.0, (min(b, end) - a) * pps - 1.5)
        doubt = " doubt" if i in take.doubt else ""
        if kind == "ghost":
            return f'<rect class="ghost" x="{number(x)}" y="{number(y)}" width="7" height="{number(tall)}" rx="1.5"/>'
        fade = number(0.4 + 0.6 * n["confidence"])
        return (f'<g class="heard{doubt}" opacity="{fade}"><path class="rang" d="M{number(x)} {number(y + tall / 2)}h{number(long)}"/>'
                f'<rect x="{number(x)}" y="{number(y)}" width="7" height="{number(tall)}" rx="1.5"/></g>')

    heard = "".join(block(i, False, "heard") for i in shown)
    # Placing in bars: where each note was heard stays as an outline, and the note itself moves onto the grid.
    placed = "".join(block(i, False, "ghost") for i in shown) + "".join(block(i, True, "heard") for i in shown)
    marks, bottom = tab_marks(take, [x0 + take.tick_time(take.notes[i]["start"]) * pps for i in shown], 50, 20, 14, shown)
    bar_lines = "".join(f'<path class="bar" d="M{number(x0 + b * pps - 9)} 50V{bottom}"/>' for b in take.bars if b <= end + 0.01)
    frames = [("", f'<path class="wave" d="{wave}"/>'),
              ("beats", f'<path class="wave faint" d="{wave}"/>{beats}{bar_numbers}'),
              ("transcribe", f"{faint_beats}{heard}"),
              ("notes", f"{beats}{bar_numbers}{placed}"),
              ("arrange", f"{bar_lines}{bar_numbers}{marks}")]
    names = {}
    for s in take.job["stages"]:
        names.setdefault(s["kind"], []).append(s["name"])
    facts = take.facts(page.lang)
    items = []
    for n, ((kind, body), text) in enumerate(zip(frames, t), 1):
        said = " · ".join(f"<code>{esc(name)}</code>" for name in names.get(kind, []))
        engine = f'<p class="stage-engine">{w["engine_stage"].format(name=said)}</p>' if said else ""
        items.append(f"""  <li class="stage">
    <div class="stage-text">
      <p class="stage-count">{w["stage"].format(n=n, total=len(frames))}</p>
      <h3>{text["title"]}</h3>
      <p>{text["text"].format(**facts)}</p>
      {engine}
    </div>
    <svg class="stage-figure tab-ink" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(text["alt"].format(**facts))}">{body}</svg>
  </li>""")
    return (f'<ol class="stages" data-stages data-previous="{w["previous"]}" data-next="{w["next"]}" data-steps="{w["steps"]}">\n' + "\n".join(items) + "\n</ol>")


def tabdemo(page, data: str, fixture: str) -> str:
    """The tab viewer: the engine's tab of a take, drawn so the page can show another tuning of the same notes."""
    w, words = WORDS[page.lang], page.product.data[page.lang]["tabdemo"]
    demo = json.loads((ROOT / data).read_text())
    variant = demo["variants"][demo["default"]]
    per_bar = demo["meter"]["beats"] * demo["ticks_per_beat"]
    # Notes are buttons: 24 px each way, and no two closer than that (an eighth note is 12 ticks).
    k, x0, top, gap = 2.2, 40, 52, 26
    strings = len(variant["open"])
    last = max(n[1] + n[2] for n in demo["notes"])
    bars = math.ceil(last / per_bar)
    width, bottom = math.ceil(x0 + bars * per_bar * k + 16), top + gap * (strings - 1)
    out = [f'<path class="string" d="M10 {top + gap * s}H{width - 10}"/>' for s in range(strings)]
    for b in range(bars + 1):
        out.append(f'<path class="bar" d="M{number(x0 + b * per_bar * k - 20)} {top}V{bottom}"/>')
        if b < bars:
            out.append(f'<text class="bar-no" x="{number(x0 + b * per_bar * k - 16)}" y="{top - 34}">{b + 1}</text>')
    lost = 0
    for i, (note, place) in enumerate(zip(demo["notes"], variant["places"])):
        x = number(x0 + note[1] * k)
        # A note with no place on the neck is a "!" under the lines; one the solver left out of the fingering, a dash.
        out_ = "!" if place[2] else "–" if place[0] is None else ""
        lost += place[2]
        y = bottom + 30 if out_ else top + gap * (place[0] - 1)
        classes = "note" + (" doubt" if note[3] else "") + (" lost" if out_ else "")
        out.append(f'<g class="{classes}" data-i="{i}" transform="translate({x} {y})"><rect class="knock" x="-12" y="-12" width="24" height="24" rx="4"/>'
                   f'<text class="fret" y="5.5">{out_ or place[1]}</text></g>')
        if note[3]:
            out.append(f'<text class="mark" x="{x}" y="{top - 16}">?</text>')
    tunings = "".join(f'<option value="{p}"{" selected" if demo["default"].startswith(p + "/") else ""}>{esc(demo["variants"][p + "/0"]["tuning"])}</option>'
                      for p in demo["presets"])
    capos = "".join(f'<option value="{c}">{w["no_capo"] if c == 0 else w["capo_n"].format(n=c)}</option>' for c in demo["capos"])
    capo = f'<label><span class="vh">{w["capo"]}</span> <select data-capo>{capos}</select></label>' if len(demo["capos"]) > 1 else ""
    label = w["tab_label"].format(title=demo["title"], bars=bars, tuning=variant["tuning"])
    start = (words["summary_lost"] if lost > 1 else words["summary_lost_one"] if lost else words["summary"]).format(tuning=variant["tuning"], capo=w["no_capo"].lower(), lost=lost)
    text_tab = esc((ROOT / fixture / "tab.txt").read_text().rstrip())
    config = {"top": top, "gap": gap, "bottom": bottom, "bars": bars, "label": w["tab_label"], "noCapo": w["no_capo"].lower(), "words": words}
    legend = "".join(f"<li><b>{mark}</b> {words[key]}</li>" for mark, key in (("?", "legend_doubt"), ("!", "legend_lost"), ("–", "legend_left")))
    return f"""<div class="tabdemo" data-src="@/assets/data/{Path(data).name}" data-tabdemo="{esc(json.dumps(config, separators=(",", ":"), ensure_ascii=False))}">
  <div class="tabdemo-controls" hidden>
    <label>{w["tuning"]} <select data-tuning>{tunings}</select></label>
    {capo}
  </div>
  <div class="tabdemo-scroll" role="region" aria-label="{esc(w["tab_scroll"])}" tabindex="0">
    <svg class="tab-ink" width="{width}" height="{bottom + 48}" viewBox="0 0 {width} {bottom + 48}" role="img" aria-label="{esc(label)}">{"".join(out)}</svg>
  </div>
  <ul class="tabdemo-legend">{legend}</ul>
  <div class="tabdemo-chosen">
    <p class="tabdemo-status" data-status role="status">{start}</p>
    <div class="neck" data-neck hidden></div>
  </div>
  <p class="tabdemo-hint" hidden>{w["pick"]}</p>
  <details><summary>{w["as_text"].format(tuning=variant["tuning"])}</summary><pre tabindex="0" role="region" aria-label="{esc(w["as_text"].format(tuning=variant["tuning"]))}">{text_tab}</pre></details>
</div>"""


def dots(page, path: str, file: str = "eval/baselines.json", kind: str = "") -> str:
    """A hundred squares with a share of them filled: a measured rate from a data file, as so many of 100."""
    n = round(float(lookup(file, path)) * 100)
    cells = "".join(f'<rect class="{"on" if i < n else "off"}" x="{(i % 10) * 12}" y="{(i // 10) * 12}" width="10" height="10" rx="1"/>' for i in range(100))
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
      <caption id="matrix-caption-{page.product.id}" class="vh">{w["table"].format(name=page.product.data[lang]["name"])}</caption>
      <thead><tr><th scope="col">{w["platform"]}</th><th scope="col">{w["alone"]}</th><th scope="col">{w["with_bandroom"]}</th></tr></thead>
      <tbody>{body}
      </tbody>
    </table>
  </div>
</div>"""
