"""Figures the pages ask for with {{figure <name> …}}: drawn at build time from files in the repository (a product's
take, eval/baselines.json), so what a page shows is what the engine answered.

Each figure is complete without JavaScript; site/shared/showcase.js makes it something to play with.
A product's own figures live in site/<product>/figures.py, with the same shape: name(page, **args) -> HTML.
A figure takes its words from the page (page.say), in the language the page is being written in.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


class Sound:
    """The loudness of a take's recording, fifty times a second (a product's figures/sound.json)."""

    def __init__(self, path: Path):
        heard = json.loads(path.read_text())
        self.peaks, self.rate = heard["peak"], heard["per_second"]

    def level(self, t: float, width: float) -> float:
        """How loud the take is from a second on, for `width` seconds: the highest peak there."""
        a, b = int(t * self.rate), max(int(t * self.rate) + 1, int((t + width) * self.rate))
        return max(self.peaks[a:b], default=0.0)


def beat_seconds(beats: list[float], beat: float) -> float:
    """The second a beat falls on, counted from the first beat the engine found (0), between those beats or past them."""
    i = max(0, min(math.floor(beat), len(beats) - 2))
    return beats[i] + (beat - i) * (beats[i + 1] - beats[i])


def bar_times(beats: list[float], per_bar: int, first_downbeat: int, end: float) -> list[float]:
    """Where each bar starts in the recording, from bar 1, and last where the last bar ends (the end of the recording).
    `first_downbeat` is the engine's: which of its beats is the first beat of a bar. A take that starts with an upbeat
    has it below 0, and its bar 1 starts on the upbeat."""
    if not -per_bar < first_downbeat <= 0:
        raise SystemExit(f"the take's first beat is not in its bar 1 (first downbeat {first_downbeat}, {per_bar} beats a bar)")
    starts = [max(0, i) for i in range(first_downbeat, len(beats), per_bar)]
    return [round(beats[i], 3) for i in starts] + [round(end, 3)]


def bar_beat(i: int, per_bar: int, first_downbeat: int) -> tuple[int, int]:
    """The bar and the beat in it (both from 1) of the engine's beat number i."""
    k = i - first_downbeat
    return k // per_bar + 1, k % per_bar + 1


def beat_grid(beats: list[float], per_bar: int, first_downbeat: int, x, end: float, bottom: float, faint: bool = False) -> str:
    """The beats up to `end` as upright lines, the first beat of a bar darker, with the bar's number over where it
    starts (bar 1 over its first beat, an upbeat too)."""
    out = []
    for i, b in enumerate(beats):
        if b > end + 0.01:
            break
        bar, beat = bar_beat(i, per_bar, first_downbeat)
        out.append(f'<path class="beat{" down" if beat == 1 else ""}{" faint" if faint else ""}" d="M{number(x(b))} 26V{number(bottom)}"/>')
        if (beat == 1 or i == 0) and b < end - 0.1:
            out.append(f'<text class="bar-no" x="{number(x(b) + 3)}" y="16">{bar}</text>')
    return "".join(out)


class Take:
    """What the engine answered for a tab, as a product keeps it (site/<product>/take), and its recording's loudness."""

    def __init__(self, product):
        folder = product.dir / "take"
        self.tab = json.loads((folder / "tab.json").read_text())
        self.about = json.loads((folder / "take.json").read_text())
        self.heard = json.loads((folder / "heard.json").read_text())
        composition = json.loads((folder / "composition.json").read_text())
        self.title = self.about["title"]
        self.beats = composition["beat_times"]
        self.first = composition.get("first_downbeat", 0)
        self.per_bar = self.tab["meter"]["beats"]
        self.notes = self.tab["notes"]
        self.strings = len(self.tab["instrument"]["tuning"]["strings"])
        self.end = self.about["seconds"]
        self.doubt = doubtful((folder / "tab.musicxml").read_text())
        self.lost = [i for i, n in enumerate(self.notes) if n["out_of_range"]]
        self.times = bar_times(self.beats, self.per_bar, self.first, self.end)
        self.bars = self.times[:-1]
        self.sound = Sound(product.dir / "figures" / "sound.json")
        self.level = self.sound.level

    def tick_time(self, tick: float) -> float:
        """The second a tick of the written music falls on, from the beats the engine found."""
        return beat_seconds(self.beats, tick / self.tab["ticks_per_beat"] + self.first)

    def facts(self) -> dict:
        own = next((s for s in self.tab["tuning_suggestions"] if s["preset"] == self.tab["preset"]), {})
        return {"title": self.title, "tempo": round(self.tab["tempo_bpm"]), "beats": self.per_bar, "unit": self.tab["meter"]["beat_unit"],
                "notes": len(self.notes), "doubt": len(self.doubt), "lost": len(self.lost), "open": own.get("open_notes", 0),
                "tuning": self.tab["instrument"]["tuning"]["name"], "strings": self.strings, "bars": len(self.bars)}


def wave_path(sound, x_of, start: float, end: float, mid: float, height: float, step: float = 3.0) -> str:
    """A recording's loudness as upright strokes. x_of(seconds) says where a moment is drawn."""
    parts, t, width = [], start, None
    x = x_of(start)
    last = x_of(end)
    while x <= last:
        # the stretch of time this stroke stands for: found by stepping the time until the next stroke's place
        t2 = t
        while x_of(t2) < x + step and t2 < end + 1:
            t2 += 0.01
        a = max(0.8, sound.level(t, max(0.02, t2 - t)) * height / 2)
        parts.append(f"M{number(x)} {number(mid - a)}V{number(mid + a)}")
        x, t = x + step, t2
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


def strip_px(config: dict, seconds: float) -> float:
    """How far a strip's music has moved at a moment: showcase.js's px, at build time. Tab runs straight in time;
    engraved notation brings its own seconds-to-pixels points."""
    if "map" not in config:
        return seconds * config["pps"]
    points = config["map"]
    found = next((i for i, (at, _) in enumerate(points) if at >= seconds), len(points) - 1)
    i = max(1, found)
    (t0, x0), (t1, x1) = points[i - 1], points[i]
    return x1 if t1 == t0 else x0 + (x1 - x0) * (min(seconds, t1) - t0) / (t1 - t0)


def strip_frame(page, config: dict, ink: str, wave: str, width: int, height: int, label: str, note: str, classes: str = "", style: str = "",
                header: str = "") -> str:
    """The strip every app's page opens with: the recording as sound on the right of a pen and as written music on
    the left. Play gives the recording itself; the other button, the notes that were written."""
    say = page.say
    config = {**config, "barBeat": say("fig.bar_beat"), "play": say("fig.play"), "pause": say("fig.pause")}
    audio = f' data-audio="{config.pop("audio")}"' if "audio" in config else ""
    # Where the music stands at its start and part way through (as showcase.js's px puts it), so the page is drawn
    # where the script will begin, or where it rests without the script.
    style = f" --t-start: {number(strip_px(config, 0.0))}; --t-still: {number(strip_px(config, config['dur'] * 0.4))};{style}"
    # The stage clips its music in the markup itself, so a wide strip never widens the page while the styles load.
    return f"""<figure class="strip {classes}"{audio} data-strip="{esc(json.dumps(config, separators=(",", ":")))}" style="--strip-height: {height}px;{style}">
  <div class="strip-stage" style="overflow: hidden" role="img" aria-label="{esc(label)}">
    <div class="strip-ink">{ink}</div>
    <div class="strip-sound"><svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false"><path class="wave" d="{wave}"/></svg></div>
    <div class="strip-pen" aria-hidden="true"></div>
    <span class="strip-part" aria-hidden="true">{header}</span>
  </div>
  <div class="strip-controls await-js">
    <button type="button" class="button outline" data-strip-play>{say("fig.play")}</button>
    <div class="strip-hear" role="group" aria-label="{esc(say("fig.hear"))}">
      <button type="button" data-hear="recording" aria-pressed="true">{say("fig.hear_recording")}</button>
      <button type="button" data-hear="written" aria-pressed="false">{say("fig.hear_written")}</button>
    </div>
    <label class="strip-range"><span class="vh">{say("fig.position")}</span><input type="range" min="0" max="{config["dur"]}" step="0.25" value="0"></label>
    <output aria-live="off">{say("fig.bar_beat").format(bar=1, beat=1)}</output>
  </div>
  <figcaption><details class="strip-about"><summary>{say("fig.about")}</summary><p>{note}</p></details></figcaption>
</figure>"""


def strip(page) -> str:
    """The strip for a tab: straight in time, so many pixels a second."""
    take = Take(page.product)
    pps, top, gap = 112.0, 64, 22
    width = math.ceil((take.end + 0.3) * pps)
    marks, bottom = tab_marks(take, [n["onset_s"] * pps for n in take.notes], top, gap, 16)
    height = bottom + 44
    bars = "".join(f'<path class="bar" d="M{number(t * pps - 16)} {top}V{bottom}"/>'
                   f'<text class="bar-no" x="{number(t * pps - 12)}" y="{top - 34}">{i + 1}</text>' for i, t in enumerate(take.bars))
    wave = wave_path(take.sound, lambda t: t * pps, 0.0, take.end, (top + bottom) / 2, bottom - top + 40)
    facts = take.facts()
    config = {"dur": round(take.end, 2), "pps": pps, "beats": take.beats, "perBar": take.per_bar, "first": take.first, "audio": "@/assets/data/take.mp3",
              "notes": [[round(n["onset_s"], 3), round(n["offset_s"] - n["onset_s"], 3), n["pitch"]] for n in take.notes if not n["out_of_range"]]}
    ink = f'<svg class="tab-ink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false">{bars}{marks}</svg>'
    return strip_frame(page, config, ink, wave, width, height, page.say("hero.strip_label", **facts), page.say("hero.strip_note", **facts),
                       header=page.say("fig.tuning_name", tuning=facts["tuning"]))


def stage_list(page, frames: list[str], facts: dict, sounds: dict | None = None) -> str:
    """The steps as a list, each with its picture: the script shows them one at a time. `sounds` gives a step a Play
    button, by its number: {"from", "to"} plays that stretch of the recording, {"notes"} the notes that were written
    ([start, length, pitch], in seconds)."""
    say, texts, sounds = page.say, page.say("steps.items"), sounds or {}
    items = []
    for n, (frame, text) in enumerate(zip(frames, texts), 1):
        play = (f'\n      <button type="button" class="button outline stage-play await-js" data-stage-play="{n}" aria-live="off">{say("fig.play")}</button>'
                if n in sounds else "")
        items.append(f"""  <li class="stage">
    <div class="stage-text">
      <p class="stage-count">{say("fig.stage", n=n, total=len(frames))}</p>
      <h3>{text["title"]}</h3>
      <p>{text["text"].format(**facts)}</p>{play}
    </div>
    {frame.replace("{alt}", esc(text["alt"].format(**facts)))}
  </li>""")
    sound = (f' data-audio="@/assets/data/take.mp3" data-sound="{esc(json.dumps({"plays": sounds, "play": say("fig.play"), "pause": say("fig.pause"), "failed": say("fig.no_sound")}, separators=(",", ":"), ensure_ascii=False))}"'
             if sounds else "")
    return (f'<ol class="stages" data-stages data-previous="{say("fig.previous")}" data-next="{say("fig.next")}" data-steps="{say("fig.steps")}"{sound}>\n'
            + "\n".join(items) + "\n</ol>")


NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B"]


def pitch_axis(low: int, high: int, top: float, row: float) -> str:
    """Note names up the left of a piano roll, each at its row: every C in it, as a keyboard is read; where it holds
    fewer than two, its lowest, middle and highest natural notes."""
    naturals = [p for p in range(low + 1, high) if "♯" not in NAMES[p % 12] and "♭" not in NAMES[p % 12]]
    cs = [p for p in naturals if p % 12 == 0]
    picked = cs if len(cs) > 1 else sorted({naturals[0], naturals[len(naturals) // 2], naturals[-1]}) if naturals else []
    return "".join(f'<text class="axis" x="2" y="{number(top + (high - p) * row + max(6.0, row - 1.5) / 2 + 3.5)}">{NAMES[p % 12]}{p // 12 - 1}</text>'
                   for p in picked)


def roll_key(page, items: list[tuple[str, str]], y: float, width: float = 360) -> tuple[str, float]:
    """The key under a piano roll: a mark of each kind and what it is, on as many lines as it needs. Gives the key and
    the height its picture needs to hold it."""
    out, x = [], 40
    for kind, key in items:
        label = page.say(key)
        room = 30 + 6.2 * len(label)
        if x > 40 and x + room - 12 > width:
            x, y = 40, y + 16
        mark = ('<path class="move" d="M0 -3H8"/><path class="move-head" d="M12 -3l-4 -3v6z"/>' if kind == "move"
                else '<rect class="swatch" width="12" height="8" rx="2" y="-7"/>')
        out.append(f'<g class="key-{kind}" transform="translate({x} {number(y)})">{mark}<text class="key-text" x="17">{esc(label)}</text></g>')
        x += room
    return "".join(out), y + 4


def moves(heard: list, written: list, x_of, low: int, high: int, top: float, row: float, end: float, count: int = 3) -> str:
    """Arrows for the notes that moved furthest, from where they were heard to where they are written."""
    pairs = [(h, w) for h, w in zip(heard, written) if h[0] < end and w[0] < end and low <= h[2] <= high]
    pairs = sorted(pairs, key=lambda hw: -abs(x_of(hw[1][0]) - x_of(hw[0][0])))[:count]
    out = []
    for h, w in pairs:
        a, b = x_of(h[0]) + 4.5, x_of(w[0]) + 4.5
        if abs(b - a) < 6:
            continue
        y = top + (high - h[2]) * row - 5
        tip = 4 if b > a else -4
        out.append(f'<path class="move" d="M{number(a)} {number(y)}H{number(b - tip)}"/><path class="move-head" d="M{number(b)} {number(y)}l{-tip} -3v6z"/>')
    return "".join(out)


def roll(notes: list, x_of, low: int, high: int, top: float, row: float, kind: str, end: float) -> str:
    """Notes as a piano roll: each a block where it starts and a thin line for as long as it rang."""
    out = []
    for start, stop, pitch, *more in notes:
        if start >= end or not low <= pitch <= high:
            continue
        x, y, tall = x_of(start), top + (high - pitch) * row, max(6.0, row - 1.5)
        long = max(0.0, x_of(min(stop, end)) - x - 1.5)
        extra = f" {more[0]}" if more and more[0] else ""
        if kind == "ghost":
            out.append(f'<rect class="ghost" x="{number(x)}" y="{number(y)}" width="9" height="{number(tall)}" rx="2"/>')
        else:
            out.append(f'<g class="{kind}{extra}"><path class="rang" d="M{number(x)} {number(y + tall / 2)}h{number(long)}"/>'
                       f'<rect x="{number(x)}" y="{number(y)}" width="9" height="{number(tall)}" rx="2"/></g>')
    return "".join(out)


def stages(page) -> str:
    """The steps from sound to tab, each with what the engine had at that point for the take's first bar or two."""
    take = Take(page.product)
    width, height, x0 = 360, 230, 40         # room on the left for the note names of the piano rolls
    two = take.bars[2]                       # the recording and its beat: two bars
    one = take.bars[1]                       # the notes: one bar, so they can be seen on a phone
    wide = lambda end: (lambda t: x0 + t * (width - 2 * x0) / end)
    svg = lambda body, h=height: f'<svg class="stage-figure tab-ink" viewBox="0 0 {width} {h}" role="img" aria-label="{{alt}}">{body}</svg>'

    def grid(end: float, faint: bool = False) -> str:
        return beat_grid(take.beats, take.per_bar, take.first, wide(end), end, height - 14, faint)

    wave = wave_path(take.sound, wide(two), 0.0, two, 120, 170, 2.0)
    shown = [n for n in take.notes if n["onset_s"] < one - 0.05 and not n["out_of_range"]]
    low, high = min(n["pitch"] for n in shown) - 1, max(n["pitch"] for n in shown) + 1
    row = (height - 50) / (high - low + 1)
    listeners = sorted(take.heard.items(), key=lambda kv: -len(kv[1]))
    # Hearing: what each of the two listeners wrote down, one over the other.
    heard = "".join(roll(notes, wide(one), low, high, 28, row, f"heard listener-{k}", one) for k, (_, notes) in enumerate(listeners, 1))
    # Placing: where each note was heard stays as an outline, and the note itself moves onto the beat.
    as_heard = [[n["onset_s"], n["offset_s"], n["pitch"]] for n in shown]
    written = [[take.tick_time(n["start"]), take.tick_time(n["start"] + n["dur"]), n["pitch"], "doubt" if i in take.doubt else ""]
               for i, n in enumerate(take.notes) if n in shown]
    placed = (roll(as_heard, wide(one), low, high, 28, row, "ghost", one) + roll(written, wide(one), low, high, 28, row, "heard", one)
              + moves(as_heard, written, wide(one), low, high, 28, row, one))
    axis = pitch_axis(low, high, 28, row)
    # The tab: one bar, so no two numbers on a string stand closer than a sixteenth note's room.
    only = [i for i, n in enumerate(take.notes) if n["onset_s"] < one - 0.05]
    marks, bottom = tab_marks(take, [wide(one)(take.tick_time(take.notes[i]["start"])) for i in only], 62, 22, 14, only)
    bar_lines = "".join(f'<path class="bar" d="M{number(wide(one)(b) - 9)} 62V{bottom}"/>' for b in take.bars if b <= one + 0.01)
    keyed = height + 22
    key_heard, tall_heard = roll_key(page, [("listener-1", "fig.listener_1"), ("listener-2", "fig.listener_2")], keyed - 4)
    key_placed, tall_placed = roll_key(page, [("ghost", "fig.heard_here"), ("heard", "fig.written_here")]
                                       + ([("move", "fig.moved")] if 'class="move"' in placed else [])
                                       + ([("doubt", "fig.not_sure")] if any(w[3] for w in written) else []), keyed - 4)
    frames = [svg(f'<path class="wave" d="{wave}"/>'),
              svg(f'<path class="wave faint" d="{wave}"/>{grid(two)}'),
              svg(f'{grid(one, True)}{axis}{heard}{key_heard}', tall_heard),
              svg(f'{grid(one)}{axis}{placed}{key_placed}', tall_placed),
              svg(f"{bar_lines}{marks}")]
    # What can be heard: the recording of the two bars, and the notes of the bar that was written as tab.
    sounds = {1: {"from": 0, "to": round(two, 3)},
              5: {"notes": [[round(take.tick_time(take.notes[i]["start"]), 3), round(take.notes[i]["offset_s"] - take.notes[i]["onset_s"], 3), take.notes[i]["pitch"]]
                            for i in only if not take.notes[i]["out_of_range"]]}}
    return stage_list(page, frames, take.facts(), sounds)


def text_frame(page) -> dict:
    """What the plain-text tab says around its lines (the title, instrument, tuning, capo, tempo and time above, the
    key to its marks below), so the script can write the same text for the tuning that is chosen."""
    lines = (page.product.dir / "take" / "tab.txt").read_text().rstrip().splitlines()
    end = max(i for i, line in enumerate(lines) if line.endswith("||"))
    return {"head": lines[:lines.index("")], "foot": lines[end + 1:]}


def tabdemo(page) -> str:
    """The tab viewer: the engine's tab of the take, drawn so the page can show another tuning of the same notes."""
    say = page.say
    words = page.group("try.words.")
    demo = json.loads((page.product.dir / "figures" / "tab-demo.json").read_text())
    variant = demo["variants"][demo["default"]]
    per_bar = demo["meter"]["beats"] * demo["ticks_per_beat"]
    # Notes are buttons: 24 px each way, and no two closer than that (a sixteenth note is 6 ticks).
    k, x0, top, gap = 4.4, 40, 52, 26
    strings = len(variant["open"])
    last = max(n[1] + n[2] for n in demo["notes"])
    bars = math.ceil(last / per_bar)
    width, bottom = math.ceil(x0 + bars * per_bar * k + 16), top + gap * (strings - 1)
    out = [f'<path class="string" d="M10 {top + gap * s}H{width - 10}"/>' for s in range(strings)]
    for b in range(bars + 1):
        out.append(f'<path class="bar" d="M{number(x0 + b * per_bar * k - 20)} {top}V{bottom}"/>')
        if b < bars:
            out.append(f'<text class="bar-no" x="{number(x0 + b * per_bar * k - 16)}" y="{top - 34}">{b + 1}</text>')
    lost = left = 0
    for i, (note, place) in enumerate(zip(demo["notes"], variant["places"])):
        x = number(x0 + note[1] * k)
        # A note with no place on the neck is a "!" under the lines; one left out of the fingering, a dash.
        mark = "!" if place[2] else "–" if place[0] is None else ""
        lost, left = lost + place[2], left + (place[0] is None and not place[2])
        y = bottom + 30 if mark else top + gap * (place[0] - 1)
        classes = "note" + (" doubt" if note[3] else "") + (" lost" if mark else "")
        out.append(f'<g class="{classes}" data-i="{i}" transform="translate({x} {y})"><rect class="knock" x="-12" y="-12" width="24" height="24" rx="4"/>'
                   f'<text class="fret" y="5.5">{mark or place[1]}</text></g>')
        if note[3]:
            out.append(f'<text class="mark" x="{x}" y="{top - 16}">?</text>')
    # The tunings as one row of buttons, the one shown pressed; with JavaScript off the tab stays in its first.
    tunings = "".join(f'<button type="button" data-value="{p}" role="radio" aria-checked="{str(demo["default"].startswith(p + "/")).lower()}">{esc(demo["variants"][p + "/0"]["tuning"])}</button>'
                      for p in demo["presets"])
    # Where each bar starts in the recording, and where the last one ends: "Play this bar" plays that stretch.
    take = Take(page.product)
    times = [round(take.tick_time(b * per_bar), 3) for b in range(bars)] + [round(take.end, 3)]
    label = say("fig.tab_label", title=say("take.title"), bars=bars, tuning=variant["tuning"])
    start = (words["summary_lost"] if lost > 1 else words["summary_lost_one"] if lost else words["summary"]).format(tuning=variant["tuning"], lost=lost)
    text_tab = esc((page.product.dir / "take" / "tab.txt").read_text().rstrip())
    config = {"top": top, "gap": gap, "bottom": bottom, "bars": bars, "title": say("take.title"), "label": say("fig.tab_label"), "words": words,
              "times": times, "asText": say("fig.as_text"), "play": say("fig.play_bar"), "pause": say("fig.pause"), "failed": say("fig.no_sound"), "text": text_frame(page)}
    # The legend names only the marks this tab can show.
    every = [p for v in demo["variants"].values() for p in v["places"]]
    marks = [("?", "legend_doubt", any(n[3] for n in demo["notes"])), ("!", "legend_lost", any(p[2] for p in every)),
             ("–", "legend_left", any(p[0] is None and not p[2] for p in every))]
    legend = "".join(f"<li><b>{mark}</b> {words[key]}</li>" for mark, key, there in marks if there)
    as_text = say("fig.as_text", tuning=variant["tuning"])
    return f"""<div class="tabdemo" data-src="@/assets/data/tab-demo.json" data-audio="@/assets/data/take.mp3" data-tabdemo="{esc(json.dumps(config, separators=(",", ":"), ensure_ascii=False))}">
  <div class="tabdemo-controls await-js">
    <span class="seg-label" id="tuning-label-{page.lang}">{say("fig.tuning")}</span>
    <div class="seg" role="radiogroup" aria-labelledby="tuning-label-{page.lang}" data-tuning>{tunings}</div>
  </div>
  <div class="tabdemo-scroll" role="region" aria-label="{esc(say("fig.tab_scroll"))}" tabindex="0">
    <svg class="tab-ink" width="{width}" height="{bottom + 48}" viewBox="0 0 {width} {bottom + 48}" role="img" aria-label="{esc(label)}">{"".join(out)}</svg>
  </div>
  <ul class="tabdemo-legend">{legend}</ul>
  <div class="tabdemo-chosen">
    <p class="tabdemo-status" data-status role="status">{start}</p>
    <button type="button" class="button outline bar-play await-js" data-bar-play disabled>{say("fig.play_bar")}</button>
    <div class="neck" data-neck hidden></div>
  </div>
  <p class="tabdemo-hint await-js">{say("fig.pick")}</p>
  <details><summary data-as-text>{as_text}</summary><pre tabindex="0" role="region" aria-label="{esc(as_text)}" data-plain>{text_tab}</pre></details>
</div>"""


def gets(page) -> str:
    """What the app gives you: a short list, each with a heading."""
    return '<ul class="gets">' + "".join(f"<li><h3>{item['title']}</h3><p>{item['text']}</p></li>" for item in page.say("get.items")) + "</ul>"


def screens(page) -> str:
    """The app's own screens, in the order a player meets them."""
    items = []
    for item in page.say("screens.items"):
        shot = page.shot(item["shot"], "(max-width: 520px) 44vw, 232px", "", "lazy", said=item["alt"]).replace("\n", "\n      ")
        items.append(f'  <li>\n    <div class="phone-frame">\n      {shot}\n    </div>\n    <h3>{item["title"]}</h3>\n    <p>{item["text"]}</p>\n  </li>')
    # On a phone the screens are a row that scrolls by itself, a screen at a time; the page does not.
    return (f'<div class="flow-scroll" role="region" aria-label="{esc(page.say("fig.screens"))}" tabindex="0">\n<ol class="flow">\n'
            + "\n".join(items) + "\n</ol>\n</div>")


def icon(page, size: str = "64") -> str:
    """The app's mark, beside its name: in the hero on a desktop, and on its sheet on the family home."""
    mark = Path(page.product.data["marks"][0]).name
    return f'<img class="app-icon" src="@/assets/logo/{mark}" width="{size}" height="{size}" alt="">'


def places(page, product=None) -> list[dict]:
    """Where an app runs, in the rail's order: its own places from [[variants]], with the family's Bandroom fifth."""
    product = product or page.product
    own = {v["id"]: v for v in product.data["variants"]}
    shared = {"id": "bandroom", "files": ["bandroom"], **page.site.bandroom}
    return [own[k] if k != "bandroom" else shared for k in RAIL if k in own or k == "bandroom"]


RAIL = ("phone", "tablet", "mac", "windows", "bandroom", "studio")  # the same order in every app


def tags(page, place: dict) -> str:
    """How ready each device of a place is: a word and a shape, never a colour alone. The device is named only where
    a place holds two; where it holds one, the place's own name already says it."""
    say, two = page.say, len(place["devices"]) > 1
    return (f'<ul class="tags" aria-label="{esc(say("variants.tags"))}">'
            + "".join(f'<li class="tag {d["status"]}">{f"""<span class="tag-device">{d["name"]}</span> """ if two else ""}{say("variants." + d["status"])}</li>' for d in place["devices"])
            + "</ul>")


def rail(page, product=None, base: str = "#") -> str:
    """The variant rail: one chip per place, glyph and name and a short note. A chip is a link to its place; the
    script makes the chips tabs over the panels. Bandroom's chip is dashed: it is the line's, shared by every app."""
    say, chips = page.say, []
    for v in places(page, product):
        sub = say(f"variants.{v['id']}.sub")
        shared = ' class="shared"' if v["id"] == "bandroom" else ""
        chips.append(f'<li><a href="{base}{v["id"]}"{shared} data-variant="{v["id"]}">{page.site.glyphs[v["id"]]}'
                     f'<span class="rail-name">{say(f"variants.{v["id"]}.name")}</span>{f" <small>{sub}</small>" if sub else ""}</a></li>')
    return f'<ul class="rail" aria-label="{esc(say("variants.label"))}" data-mine="{esc(say("variants.mine"))}">' + "".join(chips) + "</ul>"


def devices(page) -> str:
    """Where it runs: the rail, and a panel per place with what you do there, how ready it is, what it needs and where
    to get it. Without the script every panel is there, one under the other; with it, the chosen one."""
    say, name, panels = page.say, page.product.data["name"], []
    for v in places(page):
        w, vid = v[page.lang], v["id"]
        href = "@family/bandroom/" if vid in ("bandroom", "studio") else f"@/download/#{vid}"
        shot = ""
        if v.get("shot"):
            kind = page.product.kinds[v["shot"]]
            frame = {"phone": "phone-frame", "tablet": "tablet-frame"}.get(kind, "mac-frame" if kind == "mac" else "window")
            sizes = {"phone": "180px", "tablet": "280px"}.get(kind, "(max-width: 600px) 92vw, 520px")
            shot = f'\n    <div class="variant-shot {kind}"><div class="{frame}">{page.shot(v["shot"], sizes, "", "lazy", said=w["alt"])}</div></div>'
        panels.append(f"""  <div class="variant-panel" id="{vid}" data-variant="{vid}">
    <div class="variant-text">
      <h3>{say(f"variants.{vid}.title", app=name)}</h3>
      <p class="variant-does">{w["does"]}</p>
      {tags(page, v)}
      <p class="variant-needs">{w["needs"]}</p>
      <a class="button secondary" href="{href}">{say(f"variants.{vid}.download")}</a>
    </div>{shot}
  </div>""")
    return f'<div class="variants" data-rail-root>\n  {rail(page)}\n' + "\n".join(panels) + "\n</div>"


def matrix(page) -> str:
    """Where every Scribe app runs, as one table: an app per row, a place per column, each cell the devices and how
    ready they are, leading to that part of the app's download page. Bandroom is one row under them all."""
    say, apps = page.say, list(page.site.products.values())
    columns = [k for k in RAIL if k != "bandroom" and any(k in {v["id"] for v in q.data["variants"]} for q in apps)]
    head = "".join(f'<th scope="col">{page.site.glyphs[k]}<span>{say(f"variants.{k}.name")}</span></th>' for k in columns)
    rows = []
    for q in apps:
        own = {v["id"]: v for v in q.data["variants"]}
        cells = []
        for k in columns:
            label = say(f"variants.{k}.name")
            if k in own:
                cells.append(f'<td data-label="{esc(label)}"><a href="@{q.id}/download/#{k}">{page.site.glyphs[k]}<span class="cell-name">{label}</span>{tags(page, own[k])}</a></td>')
            else:
                cells.append(f'<td class="none" data-label="{esc(label)}"><span aria-hidden="true">–</span><span class="vh">{say("variants.none")}</span></td>')
        rows.append(f'<tr data-brand="{q.id}"><th scope="row"><span class="chip" style="--chip: var(--family-chip-{q.id})"></span>{q.data["name"]}</th>{"".join(cells)}</tr>')
    shared = {"id": "bandroom", **page.site.bandroom}
    rows.append(f'<tr class="shared"><th scope="row">{page.site.glyphs["bandroom"]}Bandroom</th><td colspan="{len(columns)}" data-label="{esc(say("variants.shared"))}">'
                f'<a href="@family/bandroom/"><span class="cell-name">{say("variants.shared")}</span>{tags(page, shared)}</a></td></tr>')
    return f"""<div class="table-scroll lines-scroll" role="region" aria-labelledby="lines-caption" tabindex="0">
  <table class="lines">
    <caption id="lines-caption" class="vh">{say("variants.matrix")}</caption>
    <thead><tr><td></td>{head}</tr></thead>
    <tbody>
      {"\n      ".join(rows)}
    </tbody>
  </table>
</div>"""


def listening(page) -> str:
    """Where a recording goes: from the app on the phone to Bandroom on your own computer and back, inside your own
    network. The arrows are the family's pen line; nothing goes to the internet."""
    w = page.group("listening.")
    t = lambda k: esc(w[k])
    return f"""<svg class="diagram diagram-home" viewBox="0 0 320 356" role="img" aria-label="{t('label')}" xmlns="http://www.w3.org/2000/svg">
  <rect class="net" x="6" y="64" width="308" height="286" rx="14"/>
  <text class="lbl" x="22" y="90">{t('network')}</text>
  <rect class="box" x="24" y="8" width="272" height="40" rx="8"/>
  <text class="t" x="160" y="33" text-anchor="middle">{t('internet')}</text>
  <rect class="box model" x="60" y="108" width="200" height="72" rx="10"/>
  <text class="t" x="160" y="139" text-anchor="middle">{t('phone')}</text>
  <text class="s" x="160" y="160" text-anchor="middle">{t('phone_does')}</text>
  <path class="arrow pen" d="M124 186 V250"/><circle class="pen-dot" cx="124" cy="256" r="4"/>
  <path class="arrow pen" d="M196 256 V192"/><circle class="pen-dot" cx="196" cy="186" r="4"/>
  <text class="s" x="114" y="226" text-anchor="end">{t('up')}</text>
  <text class="s" x="206" y="226">{t('down')}</text>
  <rect class="box model" x="40" y="264" width="240" height="72" rx="10"/>
  <text class="t" x="160" y="295" text-anchor="middle">{t('computer')}</text>
  <text class="s" x="160" y="316" text-anchor="middle">{t('computer_does')}</text>
</svg>"""


BRASS_SOLO = "targets/brass/suites/solo-instruments/metrics/"


def mean(keys: list[str] | str, base: str = "") -> float:
    """A measured rate from eval/baselines.json, or the mean of several (a group of instruments)."""
    keys = [keys] if isinstance(keys, str) else keys
    return sum(float(lookup("eval/baselines.json", base + key)) for key in keys) / len(keys)


def one_in(per_hundred: float) -> int:
    """'1 in n' for so many in a hundred, n said to one significant figure: 0.43 in 100 is 1 in 200, 9.5 is 1 in 10."""
    n = 100 / per_hundred
    return int(float(f"{n:.1g}"))


def counts(card: dict) -> dict:
    """A tally card's hundred cells: right, not right and marked with a "?", and the rest, summing to a hundred.
    A card with `missed` (Brasscribe) has no marked cells: its "?" is said as how rarely a wrong note has none."""
    if "missed" in card:
        right = round(mean(card["right"], BRASS_SOLO) * 100)
        return {"right": right, "marked": 0, "rest": 100 - right, "one_in": one_in(mean(card["missed"], BRASS_SOLO))}
    p = mean(card["right"])
    right, marked = round(p * 100), round((1 - p) * mean(card["marked"]) * 100)
    return {"right": right, "marked": marked, "rest": 100 - right - marked}


def tally(page, first: str = "", link: str = "") -> str:
    """How sure it is, as tally cards: for each situation a big number of a hundred notes, a grid of a hundred cells
    (filled: right; a "?" in the doubt colour: not right, and marked; hollow: not right, no mark) and its legend with
    the counts as text. The same component for every app; the product's [[sure]] say which measured rates. With
    first="1" and link="1" (the family home): the app's first card alone, in the app's own paper, leading to its page."""
    say, product = page.say, page.product
    cards = product.data["sure"][:1] if first else product.data["sure"]
    out = []
    for i, card in enumerate(cards, 1):
        w, c, uid = card[page.lang], counts(card), f"sure-{product.id}-{i}"
        cells = '<i class="r"></i>' * c["right"] + '<i class="q"></i>' * c["marked"] + '<i class="x"></i>' * c["rest"]
        note = f': {w["note"]}' if "note" in w else ""
        key = [f'<li class="k-r"><b>{c["right"]}</b> {say("sure.right")}</li>']
        if c["marked"]:
            key.append(f'<li class="k-q"><b>{c["marked"]}</b> {say("sure.marked")}</li>')
        key.append(f'<li class="k-x"><b>{c["rest"]}</b> {say("sure.rest")}{"" if "one_in" in c else note}</li>')
        if "one_in" in c:
            key.append(f'<li class="k-m">{say("sure.missed", n=c["one_in"])}{note}</li>')
        app = f'<p class="tally-app">{product.data["name"]}</p>\n  ' if link else ""
        more = f'\n  <p class="tally-more"><a href="@/#sure">{say("sure.more", app=product.data["name"])}</a></p>' if link else ""
        out.append(f"""<article class="tally" aria-labelledby="{uid}-title"{f' data-brand="{product.id}"' if link else ""}>
  {app}<h3 id="{uid}-title">{w["title"]}</h3>
  <p class="where">{w["where"]}</p>
  <p class="big"><span class="big-n">{c["right"]}</span> <span class="big-of">{say("sure.of_first" if i == 1 else "sure.of")}</span></p>
  <div class="hundred" role="img" aria-labelledby="{uid}-key">{cells}</div>
  <ul class="key" id="{uid}-key">{"".join(key)}</ul>{more}
</article>""")
    if link:
        return "\n".join(out)
    return '<div class="sure-grid">\n' + "\n".join(out) + "\n</div>"


def measured(page) -> str:
    """One quiet link to the paper that says how the numbers were measured, when the app has one."""
    if "research" not in page.product.pages():
        return ""
    return f'<p><a href="@/how-it-works/">{page.say("sure.how")}</a></p>'


# What every app's page calls its figures; a product with its own kind of music answers to the same names.
hero, steps, viewer = strip, stages, tabdemo
