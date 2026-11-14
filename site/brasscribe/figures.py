"""Brasscribe's own figures: notation. The engraving and each note's time, place and name are made by
site/brasscribe/make_take.py from a real recording; here they are put on the page."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZOOM = 1.5  # the engraving is shown this much larger than Verovio drew it


def score() -> dict:
    return json.loads((HERE / "figures" / "score.json").read_text())


def composition() -> dict:
    return json.loads((HERE / "take" / "composition.json").read_text())


def sounding(comp: dict) -> list[list]:
    """Every note the engine wrote, as [start, end, pitch, voice, doubtful]: in seconds, from where it was heard, or
    from its place in the bar where the engine kept no time for it."""
    beats, per, first = comp["beat_times"], comp["ticks_per_beat"], comp["first_downbeat"]

    def when(tick: float) -> float:
        # Tick 0 is the first beat of bar 1, which in a take that starts with an upbeat comes before the recording.
        whole = tick / per + first
        i = max(0, min(len(beats) - 2, math.floor(whole)))
        return beats[i] + (whole - i) * (beats[i + 1] - beats[i])

    out = []
    for v in comp["voices"]:
        for n in v["notes"]:
            start = n["onset_s"] if n.get("onset_s") is not None else when(n["start"])
            end = n["offset_s"] if n.get("offset_s") is not None else when(n["start"] + n["dur"])
            out.append([start, end, n["pitch"], v["role"], n["confidence"] < 0.759 and v["role"] == "melody", when(n["start"]), when(n["start"] + n["dur"])])
    return out


def engraving(name: str, first: bool, crop: float | None = None, label: tuple[str, str] | None = None) -> tuple[str, int, int]:
    """An engraved part for the page. Only the first use of a part on a page keeps its glyphs; the others draw with them.
    `label` is the part's name as engraved and as the page's language says it."""
    svg = (HERE / "figures" / name).read_text().strip()
    if label:
        svg = svg.replace(f">{label[0]}<", f">{label[1]}<")
    width, height = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
    if not first:
        svg = re.sub(r"<defs>.*?</defs>", "", svg, flags=re.S)
        svg = re.sub(r'<g id="[^"]*" class="note', '<g class="note', svg)
    if crop:
        inner = re.search(r'(class="definition-scale" viewBox=")0 0 (\d+) (\d+)"', svg)
        svg = svg.replace(inner.group(0), f'{inner.group(1)}0 0 {round(int(inner.group(2)) * crop)} {inner.group(3)}"')
        svg = svg.replace(f'viewBox="0 0 {width} {height}"', f'viewBox="0 0 {round(width * crop)} {height}"', 1)
        width = round(width * crop)
    return svg, width, height


def bars(page, data: dict) -> list[float]:
    """Where each bar starts in the recording and, last, where the last bar ends; checked against the bar and the beat
    the score gives every note, so a bar that would start on the wrong beat fails the build."""
    shared, comp = page.shared, composition()
    first, per, beats = comp["first_downbeat"], data["per_bar"], data["beats"]
    end = json.loads((HERE / "take" / "take.json").read_text())["seconds"]
    times = shared.bar_times(beats, per, first, end)
    for part in data["parts"]:
        for n in part["notes"]:
            if n[6] != "0/1":
                continue
            i = first + (n[4] - 1) * per + n[5] - 1
            if not 0 <= i < len(beats) or abs(n[0] - beats[i]) > 0.25 * (beats[1] - beats[0]):
                raise SystemExit(f'{part["name"]["en"]}: the note at {n[0]} s is bar {n[4]}, beat {n[5]}, but that beat is not there in the take')
    return times


def named(part: dict, lang: str) -> tuple[str, str]:
    return part["name"]["en"], part["name"][lang]


def interpolate(points: list, value: float) -> float:
    for (a, b), (c, d) in zip(points, points[1:]):
        if value <= c:
            return b + (d - b) * (value - a) / (c - a) if c != a else b
    return points[-1][1]


def timeline(part: dict, width: float, end: float) -> list[list[float]]:
    """Seconds against pixels along the engraved line: the notes where they are drawn, and a little before and after."""
    points = [[round(n[0], 3), round(n[2] * width, 1)] for n in part["notes"]]
    return [[0.0, round(points[0][1] - 60, 1)], *points, [round(end, 3), round(width - 8, 1)]]


def facts(page, data: dict) -> dict:
    comp, lead = composition(), data["parts"][0]
    return {"title": page.say("take.title"), "part": lead["name"][page.lang], "notes": len(lead["notes"]), "doubt": sum(n[3] for n in lead["notes"]),
            "bars": len(bars(page, data)) - 1, "beats": data["per_bar"], "tempo": round(60 / (data["beats"][2] - data["beats"][1])),
            "parts": len(data["parts"]), "all": sum(len(v["notes"]) for v in comp["voices"])}


def hero(page) -> str:
    """The hero: the quartet's recording as sound on the right of the pen and as the 1st Cornet's part on the left."""
    shared, data = page.shared, score()
    part = data["parts"][0]
    about = json.loads((HERE / "take" / "take.json").read_text())
    svg, width, height = engraving(f'part-{part["id"]}.svg', True, None, named(part, page.lang))
    width, height = round(width * ZOOM), round(height * ZOOM)
    points = timeline(part, width, about["seconds"])
    sound = shared.Sound(HERE / "figures" / "sound.json")
    wave = shared.wave_path(sound, lambda t: interpolate(points, t), 0.0, about["seconds"], height * 0.56, height * 0.72)
    comp = composition()
    written = [[round(n[0], 3), round(n[1] - n[0], 3), n[2]] for n in sounding(comp)]
    config = {"dur": about["seconds"], "map": points, "beats": data["beats"], "perBar": data["per_bar"], "first": comp["first_downbeat"], "notes": written, "voice": "brass",
              "audio": "@/assets/data/take.mp3"}
    ink = svg.replace("<svg ", f'<svg class="score-ink" width="{width}" height="{height}" aria-hidden="true" focusable="false" ', 1)
    f = facts(page, data)
    return shared.strip_frame(page, config, ink, wave, width, height, page.say("hero.strip_label", **f), page.say("hero.strip_note", **f),
                              "score-strip", header=part["name"][page.lang])


def steps(page) -> str:
    """The steps from sound to score for the take's first bars."""
    shared, data, comp = page.shared, score(), composition()
    about = json.loads((HERE / "take" / "take.json").read_text())
    heard = json.loads((HERE / "take" / "heard.json").read_text())
    sound = shared.Sound(HERE / "figures" / "sound.json")
    beats, per_bar, first = data["beats"], data["per_bar"], comp["first_downbeat"]
    width, height, x0 = 360, 230, 40         # room on the left for the note names of the piano rolls
    end = bars(page, data)[3]               # bar 1 (the upbeat), bars 2 and 3
    x = lambda t: x0 + t * (width - 2 * x0) / end
    tall = 340  # the notes of a quartet span three octaves and more: their pictures are taller, so each note can be seen
    svg = lambda body, h=height: f'<svg class="stage-figure tab-ink" viewBox="0 0 {width} {h}" role="img" aria-label="{{alt}}">{body}</svg>'
    def grid(faint: bool = False, h: int = height) -> str:
        return shared.beat_grid(beats, per_bar, first, x, end, h - 14, faint)

    wave = shared.wave_path(sound, x, 0.0, end, 120, 170, 2.0)
    every = [n for notes in heard.values() for n in notes if n[0] < end]
    low, high = min(n[2] for n in every) - 1, max(n[2] for n in every) + 1
    row = (tall - 50) / (high - low + 1)
    # Hearing: what each of the two listeners wrote down, one over the other.
    listeners = "".join(shared.roll(notes, x, low, high, 28, row, f"heard listener-{k}", end) for k, (_, notes) in enumerate(sorted(heard.items()), 1))
    notes = sounding(comp)
    as_heard = [[n[0], n[1], n[2]] for n in notes]
    placed_notes = [[n[5], n[6], n[2], "doubt" if n[4] else ""] for n in notes]
    placed = (shared.roll(as_heard, x, low, high, 28, row, "ghost", end) + shared.roll(placed_notes, x, low, high, 28, row, "heard", end)
              + shared.moves(as_heard, placed_notes, x, low, high, 28, row, end))
    axis, keyed = shared.pitch_axis(low, high, 28, row), tall + 22
    lead = data["parts"][0]
    after = next((n for n in lead["notes"] if n[0] >= end), lead["notes"][-1])
    before = [n for n in lead["notes"] if n[0] < end][-1]
    crop = (before[2] + after[2]) / 2
    written, _, _ = engraving(f'part-{lead["id"]}.svg', False, crop, named(lead, page.lang))
    key_heard, tall_heard = shared.roll_key(page, [("listener-1", "fig.listener_1"), ("listener-2", "fig.listener_2")], keyed - 4)
    key_placed, tall_placed = shared.roll_key(page, [("ghost", "fig.heard_here"), ("heard", "fig.written_here")]
                                              + ([("move", "fig.moved")] if 'class="move"' in placed else [])
                                              + ([("doubt", "fig.not_sure")] if any(n[3] for n in placed_notes if n[0] < end) else []), keyed - 4)
    stack = "".join(engraving(f'part-{p["id"]}.svg', p is not lead, crop, named(p, page.lang))[0].replace("<svg ", '<svg class="score-ink" ', 1) for p in data["parts"])
    frames = [svg(f'<path class="wave" d="{wave}"/>'),
              svg(f'<path class="wave faint" d="{wave}"/>{grid()}'),
              svg(f'{grid(True, tall)}{axis}{listeners}{key_heard}', tall_heard),
              svg(f'{grid(False, tall)}{axis}{placed}{key_placed}', tall_placed),
              written.replace("<svg ", '<svg class="stage-figure score-ink" role="img" aria-label="{alt}" ', 1),
              f'<div class="stage-figure band" role="img" aria-label="{{alt}}">{stack}</div>']
    # What can be heard: the recording of these bars, the tune that was written, and every part together.
    lead_line = [[round(n[5], 3), round(n[6] - n[5], 3), n[2]] for n in notes if n[3] == "melody" and n[5] < end]
    every_part = [[round(n[5], 3), round(n[6] - n[5], 3), n[2]] for n in notes if n[5] < end]
    sounds = {1: {"from": 0, "to": round(end, 3)}, 5: {"notes": lead_line, "voice": "brass"}, 6: {"notes": every_part, "voice": "brass"}}
    return shared.stage_list(page, frames, facts(page, data), sounds)


def viewer(page) -> str:
    """The part viewer: every player's engraved part under each other, or one of them alone; choosing a note says
    what it is."""
    shared, data, lang, say = page.shared, score(), page.lang, page.say
    times = bars(page, data)
    words = page.group("try.words.")
    # The parts as one row of radio buttons (up to five), all of them checked first; on a phone the row scrolls.
    options = f'<button type="button" data-value="all" role="radio" aria-checked="true">{say("try.all", n=len(data["parts"]))}</button>' + "".join(
        f'<button type="button" data-value="{p["id"]}" role="radio" aria-checked="false">{p["name"][lang]}</button>' for p in data["parts"])
    stack = []
    for p in data["parts"]:
        svg, width, height = engraving(f'part-{p["id"]}.svg', False, None, named(p, lang))
        label = words["part_label"].format(name=p["name"][lang], instrument=p["instrument"][lang], notes=len(p["notes"]), bars=len(times) - 1)
        stack.append(svg.replace("<svg ", f'<svg class="score-ink" data-part="{p["id"]}" width="{width}" height="{height}" role="img" aria-label="{shared.esc(label)}" ', 1))
    odd = {n[6] for p in data["parts"] for n in p["notes"]} - {"0/1", "1/2"}
    if odd:
        raise SystemExit(f"the part viewer has no words for a note at {sorted(odd)} of a beat")
    doubt = sum(n[3] for p in data["parts"] for n in p["notes"])
    start = words["start_all"].format(n=len(data["parts"]), doubt=doubt)
    config = {"lang": lang, "words": words, "times": times, "play": say("fig.play_bar"), "pause": say("fig.pause"), "failed": say("fig.no_sound")}
    return f"""<div class="partview" data-partview="{shared.esc(json.dumps(config, separators=(",", ":"), ensure_ascii=False))}" data-src="@/assets/data/" data-audio="@/assets/data/take.mp3">
  <div class="tabdemo-controls await-js">
    <span class="seg-label" id="part-label-{lang}">{say("try.part")}</span>
    <div class="seg" role="radiogroup" aria-labelledby="part-label-{lang}" data-part>{options}</div>
  </div>
  <div class="tabdemo-scroll" role="region" aria-label="{shared.esc(say("try.scroll"))}" tabindex="0"><div class="part-stack">{"".join(stack)}</div></div>
  <div class="tabdemo-chosen">
    <p class="tabdemo-status" data-status role="status">{start}</p>
    <button type="button" class="button outline bar-play await-js" data-bar-play disabled>{say("fig.play_bar")}</button>
  </div>
  <p class="tabdemo-hint await-js">{say("try.pick")}</p>
</div>"""
