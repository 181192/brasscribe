"""Brasscribe's own figures: notation. The engraving and each note's time, place and name are made by
site/brasscribe/make_take.py from a real recording; here they are put on the page."""

from __future__ import annotations

import json
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
    beats, per = comp["beat_times"], comp["ticks_per_beat"]

    def when(tick: float) -> float:
        whole = tick / per
        i = max(0, min(len(beats) - 2, int(whole)))
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
            "bars": len(data["beats"]) // data["per_bar"] + 1, "beats": data["per_bar"], "tempo": round(60 / (data["beats"][2] - data["beats"][1])),
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
    config = {"dur": about["seconds"], "map": points, "beats": data["beats"], "perBar": data["per_bar"], "notes": written, "voice": "brass",
              "audio": "@/assets/data/take.mp3"}
    ink = svg.replace("<svg ", f'<svg class="score-ink" width="{width}" height="{height}" aria-hidden="true" focusable="false" ', 1)
    f = facts(page, data)
    return shared.strip_frame(page, config, ink, wave, width, height, page.say("hero.strip_label", **f), page.say("hero.strip_note", **f),
                              "score-strip", f" --t: {round(interpolate(points, 6.0))}")


def steps(page) -> str:
    """The steps from sound to score for the take's first bars."""
    shared, data, comp = page.shared, score(), composition()
    about = json.loads((HERE / "take" / "take.json").read_text())
    heard = json.loads((HERE / "take" / "heard.json").read_text())
    sound = shared.Sound(HERE / "figures" / "sound.json")
    beats, per_bar = data["beats"], data["per_bar"]
    width, height, x0 = 360, 230, 16
    end = beats[2 * per_bar + 1]            # the upbeat and two bars
    x = lambda t: x0 + t * (width - 2 * x0) / end
    tall = 340  # the notes of a quartet span three octaves and more: their pictures are taller, so each note can be seen
    svg = lambda body, h=height: f'<svg class="stage-figure tab-ink" viewBox="0 0 {width} {h}" role="img" aria-label="{{alt}}">{body}</svg>'
    def grid(faint: bool = False, h: int = height) -> str:
        lines = "".join(f'<path class="beat{" down" if i % per_bar == 0 else ""}{" faint" if faint else ""}" d="M{shared.number(x(b))} 26V{h - 14}"/>'
                        for i, b in enumerate(beats) if b <= end + 0.01)
        return lines

    wave = shared.wave_path(sound, x, 0.0, end, 120, 170, 2.0)
    every = [n for notes in heard.values() for n in notes if n[0] < end]
    low, high = min(n[2] for n in every) - 1, max(n[2] for n in every) + 1
    row = (tall - 50) / (high - low + 1)
    # Hearing: what each of the two listeners wrote down, one over the other.
    listeners = "".join(shared.roll(notes, x, low, high, 28, row, f"heard listener-{k}", end) for k, (_, notes) in enumerate(sorted(heard.items()), 1))
    notes = sounding(comp)
    as_heard = [[n[0], n[1], n[2]] for n in notes]
    placed_notes = [[n[5], n[6], n[2], "doubt" if n[4] else ""] for n in notes]
    placed = shared.roll(as_heard, x, low, high, 28, row, "ghost", end) + shared.roll(placed_notes, x, low, high, 28, row, "heard", end)
    lead = data["parts"][0]
    after = next((n for n in lead["notes"] if n[0] >= end), lead["notes"][-1])
    before = [n for n in lead["notes"] if n[0] < end][-1]
    crop = (before[2] + after[2]) / 2
    written, _, _ = engraving(f'part-{lead["id"]}.svg', False, crop, named(lead, page.lang))
    stack = "".join(engraving(f'part-{p["id"]}.svg', p is not lead, crop, named(p, page.lang))[0].replace("<svg ", '<svg class="score-ink" ', 1) for p in data["parts"])
    frames = [svg(f'<path class="wave" d="{wave}"/>'),
              svg(f'<path class="wave faint" d="{wave}"/>{grid()}'),
              svg(f"{grid(True, tall)}{listeners}", tall),
              svg(f"{grid(False, tall)}{placed}", tall),
              written.replace("<svg ", '<svg class="stage-figure score-ink" role="img" aria-label="{alt}" ', 1),
              f'<div class="stage-figure band" role="img" aria-label="{{alt}}">{stack}</div>']
    return shared.stage_list(page, frames, facts(page, data))


def viewer(page) -> str:
    """The part viewer: every player's engraved part under each other, or one of them alone; choosing a note says
    what it is."""
    shared, data, lang, say = page.shared, score(), page.lang, page.say
    bars = len(data["beats"]) // data["per_bar"] + 1
    words = page.group("try.words.")
    options = f'<option value="all">{say("try.all", n=len(data["parts"]))}</option>' + "".join(
        f'<option value="{p["id"]}">{p["name"][lang]}</option>' for p in data["parts"])
    stack = []
    for p in data["parts"]:
        svg, width, height = engraving(f'part-{p["id"]}.svg', False, None, named(p, lang))
        label = words["part_label"].format(name=p["name"][lang], instrument=p["instrument"][lang], notes=len(p["notes"]), bars=bars)
        stack.append(svg.replace("<svg ", f'<svg class="score-ink" data-part="{p["id"]}" width="{width}" height="{height}" role="img" aria-label="{shared.esc(label)}" ', 1))
    odd = {n[6] for p in data["parts"] for n in p["notes"]} - {"0/1", "1/2"}
    if odd:
        raise SystemExit(f"the part viewer has no words for a note at {sorted(odd)} of a beat")
    doubt = sum(n[3] for p in data["parts"] for n in p["notes"])
    start = words["start_all"].format(n=len(data["parts"]), doubt=doubt)
    config = {"lang": lang, "words": words}
    return f"""<div class="partview" data-partview="{shared.esc(json.dumps(config, separators=(",", ":"), ensure_ascii=False))}" data-src="@/assets/data/">
  <div class="tabdemo-controls await-js">
    <label>{say("try.part")} <select data-part>{options}</select></label>
  </div>
  <div class="tabdemo-scroll" role="region" aria-label="{shared.esc(say("try.scroll"))}" tabindex="0"><div class="part-stack">{"".join(stack)}</div></div>
  <p class="tabdemo-status" data-status role="status">{start}</p>
  <p class="tabdemo-hint await-js">{say("try.pick")}</p>
</div>"""


def rates(page) -> str:
    """How many wrong notes slip through without a question mark, for one brass instrument alone: a sentence and a
    picture of two hundred notes for each group of the product's [[rates]]."""
    shared, say = page.shared, page.say
    base = "targets/brass/suites/solo-instruments/metrics/"
    groups = []
    for rate in page.product.data["rates"]:
        # wrong notes with no mark in a hundred notes written, the mean over the group's instruments
        slipped = sum(shared.lookup("eval/baselines.json", f"{base}{key}.q_missed/value") for key in rate["instruments"]) / len(rate["instruments"])
        one_in = 100 / slipped
        size = 10 ** (len(str(round(one_in))) - 1)
        one_in = round(one_in / size) * size  # about 1 in 200, not 1 in 232
        wrong = max(1, round(slipped * 2))
        spread = {(k * 73 + 31) % 200 for k in range(wrong)}  # the wrong ones among the others, not in a row
        cells = "".join(f'<circle class="{"wrong" if i in spread else "right"}" cx="{5 + (i % 25) * 11}" cy="{5 + (i // 25) * 11}" r="3.6"/>' for i in range(200))
        picture = f'<svg class="twohundred" viewBox="0 0 274 87" role="img" aria-label="{shared.esc(say("sure.alt_group", k=wrong))}">{cells}</svg>'
        groups.append(f'<li><div class="rate">{picture}<p>{say("sure.group", name=rate[page.lang], n=one_in)}</p></div></li>')
    return f'<ul class="rates">{"".join(groups)}</ul>'
