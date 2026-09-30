#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the Brasscribe design system for Claude from design/.

Writes the files the Claude "Design System" artifact keeps under project/:
tokens.json in the artifact's list shape, the brand book (README.md and
section files), static component previews and their guidelines, the
stylesheet the previews use, the fonts, and every asset file. Beside
project/ it writes assets.json, the file map of the assets to upload
(group, name, source, size, media type). The output depends only on the
files under design/, so two runs give the same bytes.

    uv run design/claude/build.py                # into design/claude/out
    uv run design/claude/build.py --out DIR
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
REPO = "181192/brasscribe"

MODES = ["light", "dark", "high-contrast", "high-contrast-light", "pink", "pink-dark"]
MODE_NAMES = {
    "light": "Light",
    "dark": "Dark",
    "high-contrast": "High contrast",
    "high-contrast-light": "High contrast light",
    "pink": "Pink",
    "pink-dark": "Pink dark",
}
# brasscribe.css blocks that carry each mode's elevation overrides. Pink has none of its own:
# it takes Light's, and Pink dark takes Dark's.
ELEVATION_BLOCKS = {
    "light": ':root {',
    "dark": ':root[data-theme="dark"] {',
    "high-contrast": ':root[data-theme="high-contrast"] {',
    "high-contrast-light": ':root[data-theme="high-contrast-light"] {',
    "pink": ':root {',
    "pink-dark": ':root[data-theme="dark"] {',
}

# Mockups that render a person's computer name or a network address stay out of the artifact.
PRIVATE_IN_MOCKUP = re.compile(
    r"\b[A-Z][a-z]+'s (?:MacBook|PC|Mac)\b|\b[A-Z][a-z]+s MacBook\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|\.local\."
)

MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


# ---------- reading ----------

def read(rel: str) -> str:
    return (DESIGN / rel).read_text(encoding="utf-8")


def section(md: str, heading: str) -> str:
    """The body under the first heading that starts with `heading`, up to the next heading of the same or a higher level."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"(#+) ", line)
        if m and line[len(m.group(0)):].startswith(heading):
            level = len(m.group(1))
            out = []
            for nxt in lines[i + 1:]:
                n = re.match(r"(#+) ", nxt)
                if n and len(n.group(1)) <= level:
                    break
                out.append(nxt)
            return "\n".join(out).strip("\n")
    raise SystemExit(f"heading not found: {heading}")


def portable(md: str) -> str:
    """Markdown the artifact can show: no repository images, repository links become their text,
    and no runs of blank lines."""
    md = re.sub(r"^[ \t]*!\[[^\]\n]*\]\([^)\n]*\)[ \t]*\n", "", md, flags=re.MULTILINE)
    md = re.sub(r"!\[[^\]\n]*\]\([^)\n]*\)", "", md)
    md = re.sub(r"\[([^\]\n]+)\]\((?!https?:)[^)\n]*\)", r"\1", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip("\n")


def intro(md: str) -> str:
    """The opening paragraphs of a document: after its title, before its first list of links or section."""
    body = md.split("\n", 1)[1]
    return re.split(r"^(?:- \w+:|## )", body, maxsplit=1, flags=re.MULTILINE)[0].strip("\n")


def unsection(md: str, headings: list[str]) -> str:
    """`md` without the sections whose heading starts with one of `headings`."""
    for h in headings:
        body = section(md, h)
        md = re.sub(r"^#+ " + re.escape(h) + r".*\n+" + re.escape(body) + r"\n*", "", md, count=1, flags=re.MULTILINE)
    return md


def table_rows(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        if line.startswith("|") and not re.match(r"^\|[-| :]+\|$", line):
            rows.append([c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))])
    return rows


def css_block(css: str, opener: str) -> dict[str, str]:
    start = css.index(opener)
    body = css[start + len(opener): css.index("}", start)]
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", body))


# ---------- tokens ----------

def hex_of(value: dict) -> str:
    h = value["hex"].lower()
    if "alpha" in value:
        h += f"{round(value['alpha'] * 255):02x}"
    return h


def px(dim: dict) -> str:
    v = dim["value"]
    return f"{int(v) if float(v).is_integer() else v}{dim['unit']}"


def rgba_shadow(value) -> str:
    """A DTCG shadow as CSS, with rgba() colours (the artifact reads no slash syntax)."""
    if not value:
        return "none"
    parts = []
    for s in value:
        r, g, b = (round(c * 255) for c in s["color"]["components"])
        parts.append(f"{px(s['offsetX'])} {px(s['offsetY'])} {px(s['blur'])} {px(s['spread'])} "
                     f"rgba({r}, {g}, {b}, {s['color'].get('alpha', 1)})")
    return ", ".join(parts)


def css_shadow(value: str) -> str:
    """A brasscribe.css shadow (`rgb(0 0 0 / 0.5)`) as the artifact reads it."""
    return re.sub(r"rgb\((\d+) (\d+) (\d+) / ([\d.]+)\)", r"rgba(\1, \2, \3, \4)", value.strip())


def platform_note(ext: dict) -> str:
    p = ext.get("no.brasscribe.platform")
    if not p:
        return ""
    m, w = p["material"], p["windows"]
    return (f" Apple `{p['apple']['textStyle']}` · Material `{m['role']}` ({m['sizeSp']}/{m['lineHeightSp']} sp)"
            f" · Windows `{w['style']}` ({w['sizeEpx']}/{w['lineHeightEpx']} epx).")


def build_tokens(src: dict, web_css: str) -> dict:
    colors = src["color"]
    names = [k for k in colors["light"] if not k.startswith("$")]
    color_tokens = []
    for n in names:
        color_tokens.append({
            "name": n,
            "value": {m: hex_of(colors[m][n]["$value"]) for m in MODES},
            "usage": colors["light"][n].get("$description", ""),
        })

    root = css_block(web_css, ":root {")
    families = {k: root[f"bc-font-{k}"] for k in ("text", "display", "mono")}
    fonts = []
    for style in ("Regular", "Italic"):
        fonts.append({"family": "Instrument Serif", "file": f"fonts/InstrumentSerif-{style}.ttf",
                      "weight": "400", "style": style.lower() if style == "Italic" else "normal"})

    groups = {"Play": [], "Studio": []}
    for name, t in src["typography"].items():
        if name.startswith("$"):
            continue
        v = t["$value"]
        style = {
            "name": name,
            "fontSize": px(v["fontSize"]),
            "lineHeight": v["lineHeight"],
            "fontWeight": v["fontWeight"],
            "letterSpacing": px(v["letterSpacing"]),
            "usage": t.get("$description", "") + platform_note(t.get("$extensions", {})),
        }
        fam = v["fontFamily"].strip("{}").split(".")[-1]
        if fam != "text":
            style["family"] = fam
        groups["Studio" if name.startswith("studio-") else "Play"].append(style)

    spacing = [{"name": f"space-{k}", "value": px(t["$value"]),
                "usage": f"{px(t['$value'])} on the 4 px spacing scale; Studio keeps to multiples of `space-2`."}
               for k, t in src["space"].items()]
    sizes = [{"name": k, "value": px(t["$value"]),
              "usage": t.get("$description", f"{px(t['$value'])} icon." if k.startswith("icon-") else "")}
             for k, t in src["size"].items()]
    radius = [{"name": f"radius-{k}", "value": px(t["$value"]), "usage": t.get("$description", "")}
              for k, t in src["radius"].items()]

    shadows = []
    for k, t in src["elevation"].items():
        value = {}
        for m in MODES:
            block = css_block(web_css, ELEVATION_BLOCKS[m])
            css = block.get(f"bc-elevation-{k}")
            value[m] = css_shadow(css) if (css and m != "light") else rgba_shadow(t["$value"])
        shadows.append({"name": f"elevation-{k}", "value": value, "usage": t.get("$description", "")})

    score = [{"name": f"score-{k}", "value": px(t["$value"]) if isinstance(t["$value"], dict) else str(t["$value"]),
              "usage": t.get("$description", f"Score view: {k.replace('-', ' ')}.")}
             for k, t in src["score"].items()]
    motion = src["motion"]
    duration = [{"name": f"duration-{k}", "value": px(t["$value"]), "usage": t.get("$description", "No animation.")}
                for k, t in motion["duration"].items()]
    easing = [{"name": f"easing-{k}", "value": "cubic-bezier({})".format(", ".join(f"{x:g}" for x in t["$value"])),
               "usage": {"standard": "Presses, toggles, sheets and screen changes.",
                         "enter": "Things arriving.", "exit": "Things leaving."}.get(k, "")}
              for k, t in motion["easing"].items()]

    return {
        "name": "Brasscribe",
        "version": 1,
        "meta": {
            "source": "github",
            "repo": REPO,
            "package": "design",
            "paths": {
                "tokens": ["design/tokens/tokens.json", "design/dist/web/brasscribe.css"],
                "fonts": ["design/brand/fonts"],
                "assets": ["design/brand/logo", "design/brand/icon", "design/dist/web/icons", "design/mockups/png",
                           "design/brand/social"],
                "docs": ["design/README.md", "design/system.md", "design/brand/brand.md", "design/music-stand.md"],
            },
            "generator": "design/claude/build.py",
        },
        "color": {"themes": [{"id": m, "name": MODE_NAMES[m]} for m in MODES], "tokens": color_tokens},
        "type": {"fonts": fonts, "families": families,
                 "groups": [{"name": g, "family": "text", "styles": s} for g, s in groups.items()]},
        "spacing": {"tokens": spacing},
        "radius": {"tokens": radius},
        "shadow": {"tokens": shadows},
        "size": {"tokens": sizes},
        "score": {"tokens": score},
        "duration": {"tokens": duration},
        "easing": {"tokens": easing},
    }


# ---------- icons and the mark, inlined into previews ----------

def load_icons() -> dict[str, str]:
    return dict(re.findall(r'"([\w-]+)":\s*"([^"]+)"', read("dist/web/icons.js")))


def mark_path() -> str:
    return re.search(r' d="([^"]+)"', read("brand/logo/mark.svg")).group(1)


# ---------- stylesheet ----------

MOCKUP_SECTIONS = [
    "icons", "type", "buttons", "surfaces", "list rows", "chips and toggles", "chooser", "progress",
    "uncertainty marks", "player bar", "sheets", "notices", "labelled mixer toggles", "status line", "disclosure",
]
# Only the component rules of each sheets section; the phone frame's scrim and sheet stay out.
DROP_RULES = (".scrim ", ".sheet ", ".grabber ")


def mockup_sections(css: str) -> dict[str, str]:
    out = {}
    parts = re.split(r"^/\* -{10} (.+?) -{10} \*/\n", css, flags=re.MULTILINE)
    for title, body in zip(parts[1::2], parts[2::2]):
        out[title.split(" (")[0].split(":")[0].strip()] = body.strip("\n")
    return out


def build_css(tokens: dict, mockup_css: str) -> str:
    color_names = [t["name"] for t in tokens["color"]["tokens"]]
    bridge = [f"  --bc-{n}: var(--{n});" for n in color_names]
    bridge += [f"  --bc-{t['name']}: var(--{t['name']});" for t in tokens["spacing"]["tokens"]]
    bridge += [f"  --bc-{t['name']}: var(--{t['name']});" for t in tokens["radius"]["tokens"]]
    bridge += [f"  --bc-{t['name']}: var(--{t['name']});" for t in tokens["shadow"]["tokens"]]
    bridge += [f"  --bc-{t['name']}: var(--{t['name']});" for t in tokens["score"]["tokens"]]
    bridge += [f"  --bc-font-{k}: var(--font-{k});" for k in tokens["type"]["families"]]
    # Motion has no token family in the artifact: the values are written out here.
    bridge += [f"  --bc-{t['name']}: {t['value']};" for t in tokens["duration"]["tokens"]]
    bridge += [f"  --bc-ease-{t['name'][len('easing-'):]}: {t['value']};" for t in tokens["easing"]["tokens"]]

    head = mockup_css[: mockup_css.index("/* ----------")]
    base = "\n".join(l for l in head.splitlines()
                     if not l.startswith(("@import", "@font-face", "[data-device")) and not l.startswith("/*")
                     and not l.startswith("   ")).strip()
    base = re.sub(r"^body \{", ".pv {", base, flags=re.MULTILINE)

    secs = mockup_sections(mockup_css)
    body = []
    for name in MOCKUP_SECTIONS:
        key = next(k for k in secs if k.startswith(name))
        text = "\n".join(l for l in secs[key].splitlines() if not l.startswith(DROP_RULES))
        body.append(f"/* ---------- {name} ---------- */\n{text}")
    hc = re.search(r'^\[data-theme="high-contrast"\] \.btn\.secondary \{[^}]*\}', mockup_css, flags=re.MULTILINE).group(0)
    # High contrast has no tints, only outlines: the tonal button gets its edge in both contrast themes.
    hc = hc.replace('[data-theme="high-contrast"] .btn.secondary',
                    '[data-theme="high-contrast"] .btn.secondary, [data-theme="high-contrast-light"] .btn.secondary')

    return "\n".join([
        "/* Brasscribe components for the design system previews. Generated by design/claude/build.py",
        "   from design/mockups/mockup.css; the component rules are the mockups' own. */",
        "",
        "/* The mockups read --bc-* variables; here they point at this system's tokens. */",
        ":root, [data-theme] {",
        *bridge,
        "}",
        "",
        base,
        "",
        *body,
        "",
        "/* ---------- contrast themes ---------- */",
        hc,
        "",
        "/* ---------- preview layout ---------- */",
        ".pv { padding: var(--bc-space-4); }",
        ".pv-row { display: flex; flex-wrap: wrap; gap: var(--bc-space-3); align-items: center; }",
        ".pv-col { display: flex; flex-direction: column; gap: var(--bc-space-3); }",
        ".pv-cap { font-size: 0.8125rem; color: var(--bc-text-muted); margin: 0 0 var(--bc-space-2); }",
        ".pv-narrow { max-width: 390px; }",
        ".pv-wide { max-width: 720px; }",
        ".steps .label { font: inherit; }",
        ".meta-row { display: flex; justify-content: space-between; margin-top: var(--bc-space-2); }",
        ".hero-mark { color: var(--bc-brass); }",
        ".hero-mark svg { display: block; fill: currentColor; }",
        (".err-icon { width: 56px; height: 56px; border-radius: var(--bc-radius-lg); background: var(--bc-surface); "
        "box-shadow: inset 0 0 0 1px var(--bc-border); display: grid; place-items: center; color: var(--bc-error); }"),
        ".err-icon .i { width: 28px; height: 28px; }",
        ("ul.why { margin: var(--bc-space-3) 0 0; padding-left: 1.2em; color: var(--bc-text-muted); "
        "display: flex; flex-direction: column; gap: 6px; }"),
        ".choices { display: flex; flex-direction: column; gap: var(--bc-space-3); }",
        ".legend { display: flex; flex-wrap: wrap; gap: var(--bc-space-4); align-items: center; font-size: 0.9375rem; }",
        ".legend span { display: inline-flex; gap: var(--bc-space-2); align-items: center; }",
        "",
    ])


# ---------- components ----------

def icon(icons: dict, name: str, cls: str = "i sm") -> str:
    return (f'<svg class="{cls}" viewBox="0 -960 960 960" aria-hidden="true">'
            f'<path d="{icons[name]}"/></svg>')


def components(icons: dict, mark: str) -> list[dict]:
    I = lambda n, c="i sm": icon(icons, n, c)
    return [
        {
            "name": "Button", "group": "Actions", "height": 200, "rows": ["Primary button", "Secondary / outline / plain"],
            "summary": "The one button shape: primary, secondary (tonal), outline and plain, all with 12 px corners.",
            "provides": "A verb label (Open, Record, Continue, Keep, Try again), an optional leading icon, and the one "
                        "primary per screen. Use `btn primary`, `btn secondary`, `btn outline` or `btn plain`; "
                        "`compact` (44 px) and `touch48` (48 px) change the height, `block` fills the width.",
            "note": "In both high-contrast themes the secondary button carries a 1 px `border-strong` edge, "
                    "because tints become outlines there.",
            "html": f'''<div class="pv pv-col">
  <div class="pv-row">
    <button class="btn primary">{I("import-file")}Open a recording</button>
    <button class="btn secondary">{I("record-mic")}Record with the microphone</button>
  </div>
  <div class="pv-row">
    <button class="btn outline">Cancel</button>
    <button class="btn plain">Skip</button>
    <button class="btn outline compact">Change</button>
  </div>
</div>''',
        },
        {
            "name": "ToggleChip", "group": "Actions", "height": 150, "rows": ["Player bar"],
            "summary": "An on/off practice toggle: on is a tonal fill, a 1.5 px ink edge and a ✓; off is an outline.",
            "provides": "A visible label (Count-in, Metronome, Mute my part), its icon from the Icons group, the "
                        "pressed state (`aria-pressed`) and, for Speed, the value in `val`. Add `on` when it is on. "
                        "48 pt tall in the player.",
            "note": "Never fill a toggle with ink: ink is only for the one primary.",
            "html": f'''<div class="pv pv-row player" style="box-shadow:none;background:transparent;padding:var(--bc-space-4)">
  <span class="chip" role="button" aria-pressed="false">{I("speed")}Speed <span class="val">75%</span></span>
  <span class="chip" role="button" aria-pressed="false">{I("loop")}Repeat</span>
  <span class="chip on" role="button" aria-pressed="true">{I("count-in")}Count-in</span>
  <span class="chip" role="button" aria-pressed="false">{I("metronome")}Metronome</span>
  <span class="chip on" role="button" aria-pressed="true">{I("play-along")}Mute my part</span>
</div>''',
        },
        {
            "name": "MixerToggle", "group": "Actions", "height": 150, "rows": ["Mute / only this, part picker"],
            "summary": "The labelled Mute and Only this toggles beside every part in the part picker.",
            "provides": "The part name (bold with a leading bar when it is the active part), and two toggles with "
                        "their words and icons: Mute (`mute`) and Only this (`solo`). Add `on` when on.",
            "note": "Never M/S, Solo or Demp.",
            "html": f'''<div class="pv pv-narrow">
  <div class="group">
    <div class="row"><div class="grow"><div class="title">Solo Cornet</div><div class="sub">your part</div></div>
      <span class="tg on" role="button" aria-pressed="true">{I("mute", "i")}Mute</span>
      <span class="tg" role="button" aria-pressed="false">{I("solo", "i")}Only this</span></div>
    <div class="row"><div class="grow"><div class="title">Flugel</div></div>
      <span class="tg" role="button" aria-pressed="false">{I("mute", "i")}Mute</span>
      <span class="tg" role="button" aria-pressed="false">{I("solo", "i")}Only this</span></div>
  </div>
</div>''',
        },
        {
            "name": "ListRow", "group": "Lists and surfaces", "height": 220, "rows": ["List rows"],
            "summary": "A 60 px row with a title, one subtitle line and a 40 px icon well, grouped with hairlines.",
            "provides": "A title (`title`), one subtitle line (`sub`), an icon in the `well`, and a chevron only when "
                        "the row navigates. Rows sit in a `group`.",
            "note": "",
            "html": f'''<div class="pv pv-narrow">
  <p class="eyebrow">Your scores</p>
  <div class="group">
    <div class="row"><span class="well">{I("music_note" if "music_note" in icons else "score")}</span><div class="grow"><div class="title">Old Hundredth</div><div class="sub">Brass band · 12 bars · Today · 4 to check</div></div><span class="chev">{I("open")}</span></div>
    <div class="row"><span class="well">{I("record-mic")}</span><div class="grow"><div class="title">Record with the microphone</div><div class="sub">Play your part in the room</div></div><span class="chev">{I("open")}</span></div>
  </div>
</div>''',
        },
        {
            "name": "Card", "group": "Lists and surfaces", "height": 170, "rows": ["Cards"],
            "summary": "A raised surface with 16 px corners that groups related content.",
            "provides": "The content. Never nest cards. Elevation 1 in light; a hairline in dark.",
            "note": "",
            "html": f'''<div class="pv pv-wide">
  <div class="card" style="padding: var(--bc-space-5); display:flex; gap: var(--bc-space-4); align-items:center">
    <span class="well">{I("import-file")}</span>
    <div style="flex:1"><div class="headline">Drop a recording here</div><div class="callout">MP3, WAV, M4A, MP4 and most other formats</div></div>
    <button class="btn primary">{I("import-file")}Open a recording</button>
  </div>
</div>''',
        },
        {
            "name": "Dialog", "group": "Lists and surfaces", "height": 260, "rows": ["Sheets and dialogs"],
            "summary": "A title, one sentence, then the actions; leaving never loses work silently.",
            "provides": "A title that names the choice, one sentence, and two buttons: the way forward as the "
                        "primary, bottom right on desktop. Destructive actions ask first.",
            "note": "",
            "html": '''<div class="pv">
  <div class="dialog" role="dialog" aria-labelledby="d-t" style="max-width: 420px; padding: var(--bc-space-6)">
    <h2 id="d-t" class="title-2">Finish later?</h2>
    <p style="margin-top: var(--bc-space-2)" class="muted">9 notes keep their ? marks. You can check them any time from the score.</p>
    <div class="pv-row" style="justify-content:flex-end; margin-top: var(--bc-space-6)">
      <button class="btn secondary">Keep checking</button>
      <button class="btn primary">Finish later</button>
    </div>
  </div>
</div>''',
        },
        {
            "name": "UncertaintyLegend", "group": "Score", "height": 150, "rows": ["Uncertainty legend"],
            "summary": "The ? and boxed ? marks for uncertain notes, the legend, and the score's status line.",
            "provides": "The count of notes still marked, and the link that re-opens Review. Use `q u` for "
                        "uncertain (0.4–0.7) and `q vu` for very uncertain (below 0.4), always with the words.",
            "note": "Shape plus colour, never colour alone: write \"notes marked ?\", not \"the blue notes\".",
            "html": '''<div class="pv pv-col">
  <div class="legend">
    <span><span class="q u">?</span>Brasscribe wasn't sure</span>
    <span><span class="q vu">?</span>Very unsure</span>
  </div>
  <p class="status-line"><span class="q u">?</span>9 notes marked ? · <a href="#review">Check them</a></p>
</div>''',
        },
        {
            "name": "PlayerBar", "group": "Score", "height": 230, "rows": ["Player bar"],
            "summary": "The player: round ink Play first, previous and next bar, the position, then the practice chips.",
            "provides": "The position (bar and beat), the beat counter, and the practice toggles in order: Speed, "
                        "Repeat, Count-in, Metronome, Mute my part. Chips wrap onto a second row and never clip.",
            "note": "The round 56 pt Play is the only ink control. The beat counter never flashes.",
            "html": f'''<div class="pv pv-wide">
  <div class="player">
    <div class="transport">
      <button class="icon-btn" aria-label="Previous bar">{I("previous-bar", "i")}</button>
      <button class="play" aria-label="Play">{I("play", "i")}</button>
      <button class="icon-btn" aria-label="Next bar">{I("next-bar", "i")}</button>
      <div class="pos" style="margin-left: var(--bc-space-2); flex:1"><b>Bar 13, beat 2</b> <span class="beat"><span>1</span><span class="now">2</span><span>3</span><span>4</span></span></div>
    </div>
    <div class="chips" style="margin-top: var(--bc-space-3)">
      <span class="chip">{I("speed")}Speed <span class="val">100%</span></span>
      <span class="chip">{I("loop")}Repeat</span>
      <span class="chip">{I("count-in")}Count-in</span>
      <span class="chip">{I("metronome")}Metronome</span>
      <span class="chip on">{I("play-along")}Mute my part</span>
    </div>
  </div>
</div>''',
        },
        {
            "name": "ProgressSteps", "group": "Feedback", "height": 420, "rows": ["Progress with steps"],
            "summary": "The current step in plain words, the brass progress bar, the percentage and time left, and every step.",
            "provides": "The step names in the musician's words, the percentage (\"62%\", nb \"62 %\"), the time "
                        "left, and Cancel, which confirms. Announce at most every 10% or 10 s.",
            "note": "The brass bar is the one working brand moment. With reduced motion it updates in steps.",
            "html": f'''<div class="pv pv-narrow">
  <span class="hero-mark"><svg width="40" height="40" viewBox="0 0 64 64" aria-hidden="true"><path fill-rule="evenodd" d="{mark}"/></svg></span>
  <p class="eyebrow" style="margin-top: var(--bc-space-5)">Step 4 of 6</p>
  <h1 class="display" style="font-size: 2.25rem">Writing down the notes</h1>
  <div style="margin-top: var(--bc-space-5)">
    <div class="bar" role="progressbar" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100" aria-label="Making the score"><span style="width: 62%"></span></div>
    <div class="meta-row"><span class="callout num">62%</span><span class="callout">About 2 minutes left</span></div>
  </div>
  <ol class="steps" style="margin-top: var(--bc-space-4)">
    <li class="done"><span class="dot">{I("done")}</span><span class="label">Finding the beat</span></li>
    <li class="done"><span class="dot">{I("done")}</span><span class="label">Separating the soloist from the band</span></li>
    <li class="now"><span class="dot"></span><span class="label">Writing down the notes</span></li>
    <li class="todo"><span class="dot"></span><span class="label">Laying out the pages</span></li>
  </ol>
</div>''',
        },
        {
            "name": "ErrorRecovery", "group": "Feedback", "height": 460, "rows": ["Errors with recovery"],
            "summary": "An error that says what happened, why, and the way out, with technical details collapsed.",
            "provides": "A title that says what went wrong, one or two reasons in plain words, the most likely fix as "
                        "the primary, and any command or code inside Details for the band's tech person.",
            "note": "Error colour goes on the icon only; the text stays in ink.",
            "html": f'''<div class="pv pv-narrow">
  <span class="err-icon">{I("error", "i")}</span>
  <h1 class="display" style="margin-top: var(--bc-space-5); font-size: 2.25rem">Nothing was heard</h1>
  <p style="margin-top: var(--bc-space-3)">The recording is silent. This usually means one of these:</p>
  <ul class="why">
    <li>The music app blocks recording. Streaming apps usually do.</li>
    <li>Nothing was playing while you recorded.</li>
  </ul>
  <div class="pv-col" style="margin-top: var(--bc-space-5)">
    <button class="btn primary block">{I("import-file")}Open a recording instead</button>
    <button class="btn secondary block">{I("record-mic")}Record with the microphone</button>
  </div>
  <details class="tech">
    <summary>Details for the band's tech person</summary>
    <p class="muted" style="margin-top: var(--bc-space-2)">Commands, addresses and error codes go here, collapsed by default.</p>
  </details>
</div>''',
        },
        {
            "name": "EmptyState", "group": "Feedback", "height": 240, "rows": ["Empty states"],
            "summary": "One sentence that says what will appear, the brass mark, and the action that fills it.",
            "provides": "The sentence (display face) and the one action.",
            "note": "",
            "html": f'''<div class="pv pv-narrow" style="text-align:center">
  <span class="hero-mark" style="display:inline-block"><svg width="40" height="40" viewBox="0 0 64 64" aria-hidden="true"><path fill-rule="evenodd" d="{mark}"/></svg></span>
  <p class="display" style="font-size: 1.75rem; margin-top: var(--bc-space-3)">Your scores appear here after the first recording.</p>
  <button class="btn primary" style="margin-top: var(--bc-space-5)">{I("import-file")}Open a recording</button>
</div>''',
        },
        {
            "name": "WhatIsThis", "group": "Choosers", "height": 470, "rows": ['"What is this?" chooser'],
            "summary": "The \"What is this?\" chooser: a serif question and four option cards, one chosen by a 2 px ink ring.",
            "provides": "The question, four options with one sentence each, nothing pre-selected on the first run, and "
                        "the remembered choice per song. Use `choice` in a radio group; `on` marks the chosen one.",
            "note": "",
            "html": '''<div class="pv pv-narrow">
  <h1 class="display">What is this?</h1>
  <p class="callout" style="margin-top: var(--bc-space-2); font-size: 1.0625rem">Your answer decides how Brasscribe listens. It never guesses.</p>
  <div class="choices" style="margin-top: var(--bc-space-5)" role="radiogroup" aria-label="What is this?">
    <div class="choice" role="radio" aria-checked="false"><div style="flex:1"><div class="t">One instrument</div><div class="d">One player on their own, like you practising the cornet.</div></div><span class="radio"></span></div>
    <div class="choice" role="radio" aria-checked="false"><div style="flex:1"><div class="t">Brass band</div><div class="d">A whole band playing together, with no other instruments.</div></div><span class="radio"></span></div>
    <div class="choice on" role="radio" aria-checked="true"><div style="flex:1"><div class="t">Soloist with orchestra or band</div><div class="d">You get the solo part, plus the accompaniment arranged for brass band.</div></div><span class="radio"></span></div>
    <div class="choice" role="radio" aria-checked="false"><div style="flex:1"><div class="t">Pop or rock</div><div class="d">Singing, guitars, keys, bass and drums.</div></div><span class="radio"></span></div>
  </div>
  <p class="caption" style="margin-top: var(--bc-space-3); font-size: 0.9375rem">Not sure? Choose Brass band. You can change it later.</p>
</div>''',
        },
    ]


def component_readme(c: dict, rows: dict[str, list[str]]) -> str:
    out = [c["summary"], ""]
    for r in c["rows"]:
        cells = rows[r]
        out += [f"**{r}.** {cells[1]}", ""]
    out += ["## What the consumer provides", "", c["provides"], ""]
    if c["note"]:
        out += [c["note"], ""]
    out += ["## Native controls", "", "| Platform | Control |", "|---|---|"]
    for r in c["rows"]:
        cells = rows[r]
        prefix = f"{r}: " if len(c["rows"]) > 1 else ""
        for plat, cell in zip(("SwiftUI", "Compose", "WinUI 3", "Studio HTML"), cells[2:6]):
            out.append(f"| {plat} | {prefix}{cell} |")
    out += ["", "## Brand expression", ""]
    out += [f"- {rows[r][6]}" for r in c["rows"]]
    return "\n".join(out) + "\n"


# ---------- the brand book ----------

COLOR_GROUPS = [
    ("Chrome", ["bg", "surface", "surface-raised", "text", "text-muted", "border", "border-strong", "primary",
                "on-primary", "secondary", "on-secondary", "focus", "scrim"]),
    ("Brand", ["brass", "brass-text", "brass-tint"]),
    ("Status", ["success", "warning", "error"]),
    ("Score (the score owns colour)", ["ink", "staff", "uncertain", "very-uncertain", "adlib-tint", "loop-tint",
                                       "loop-edge", "cursor", "cursor-tint", "selection-tint", "selection-edge"]),
    ("Studio data series", ["model-1", "model-2", "model-3", "model-4"]),
]


def build_readme(tokens: dict, src: dict, system: str, brand: str, readme: str, icons_json: dict) -> str:
    by_name = {t["name"]: t for t in tokens["color"]["tokens"]}
    grouped = {n for _, ns in COLOR_GROUPS for n in ns}
    groups = COLOR_GROUPS + ([("Other", [n for n in by_name if n not in grouped])] if set(by_name) - grouped else [])
    colour_lines = []
    for title, names in groups:
        colour_lines += [f"**{title}**", ""]
        colour_lines += [f"- `{n}`: {by_name[n]['usage']}" for n in names if n in by_name]
        colour_lines.append("")

    mode_lines = []
    for m in MODES:
        d = src["color"][m].get("$description")
        mode_lines.append(f"- `{m}` ({MODE_NAMES[m]}){': ' + d if d else ''}")

    type_rows = ["| Style | Size / line / weight | Use and native style |", "|---|---|---|"]
    for g in tokens["type"]["groups"]:
        for s in g["styles"]:
            type_rows.append(f"| `{s['name']}` | {s['fontSize']} / {s['lineHeight']} / {s['fontWeight']} | {s['usage']} |")

    def token_list(family: str) -> list[str]:
        return [f"- `{t['name']}` {t['value'] if isinstance(t['value'], str) else t['value']['light']}"
                f"{': ' + t['usage'] if t['usage'] else ''}" for t in tokens[family]["tokens"]]

    name_sec = re.sub(r': "Brasscribe on [^"]*" / "Brasscribe på [^"]*"\.', ".", section(brand, "Name"))
    focus_motion = section(system, "5. Components").split("\n\n", 1)[1]
    focus_motion = focus_motion[focus_motion.index("**Focus.**"):]
    contrast = re.search(r"^\*\*Contrast:\*\*.*$", readme, flags=re.MULTILINE).group(0)
    contrast = re.sub(r" See .*$", "", contrast)

    parts = [
        intro(system),
        "",
        ("Tokens keep the source's role names: the role `bg` (`color.light.bg` in `design/tokens/tokens.json`, "
        "`--bc-bg` in Studio's `brasscribe.css`) is `bg` here, `--bg` in CSS. Components use the classes in "
        "`components/bundle.css`."),
        "",
        "## Principles",
        "",
        section(readme, "Principles"),
        "",
        "## Rules that decide every doubt",
        "",
        section(system, "1. Rules that decide every doubt"),
        "",
        "## Colour",
        "",
        "Themes, primary first:",
        "",
        *mode_lines,
        "",
        contrast,
        "",
        *colour_lines,
        "### The score",
        "",
        section(system, "6. Score view"),
        "",
        "## Type",
        "",
        section(brand, "Typeface"),
        "",
        *type_rows,
        "",
        "## Spacing, size, radius and elevation",
        "",
        *token_list("spacing"),
        "",
        *token_list("size"),
        "",
        *token_list("radius"),
        "",
        *token_list("shadow"),
        "",
        "## Focus and motion",
        "",
        focus_motion,
        "",
        *token_list("duration"),
        *token_list("easing"),
        "",
        "## Layout",
        "",
        section(system, "2. Layout"),
        "",
        "## Navigation per platform",
        "",
        section(system, "4. Navigation per platform"),
        "",
        "## Using the tokens per platform",
        "",
        section(readme, "Using the tokens per platform"),
        "",
        "## Voice",
        "",
        section(brand, "Voice"),
        "",
        "## Name",
        "",
        name_sec,
        "",
        "## Mark and app icon",
        "",
        "The logo files are in the Logos group, the app icon masters in App icon, and the link preview in Social.",
        "",
        section(brand, "Mark"),
        "",
        section(brand, "App icon").split("- **Build:**")[0].rstrip(),
        "",
        "## Iconography",
        "",
        icons_json["$description"],
        "",
        "The Icons group holds each action's SVG, named by action. Its README maps every action to its label and native glyph.",
        "",
        "## Appearance",
        "",
        unsection(section(system, "10. Appearance"), ["Screenshots"]),
        "",
        "## Studio: the workbench variant",
        "",
        section(system, "7. Studio"),
        "",
        "## Brasscribe Bandroom",
        "",
        section(system, "8. Brasscribe Bandroom"),
        "",
        "## Music stand",
        "",
        section(system, "9. Music stand"),
        "",
        "## Components",
        "",
        ("Each card under Components is a static rendition of a component from the mockups, with its rule, native "
        "controls and brand expression. The section \"Components on each platform\" lists every component, "
        "including the screens that have no card yet."),
    ]
    return portable("\n".join(parts)) + "\n"


def build_components_md(system: str) -> str:
    body = section(system, "5. Components")
    body = body[: body.index("**Focus.**")].rstrip()
    return portable("# Components on each platform\n\n" + body) + "\n"


def build_music_stand(md: str) -> str:
    md = unsection(md, ["2. Today", "11. Implementation plan", "12. Owner decisions"])
    return portable(md) + "\n"


# ---------- assets ----------

def mockup_pngs() -> list[Path]:
    htmls = {p.stem: p for p in (DESIGN / "mockups").glob("*.html")}
    keep = []
    for png in sorted((DESIGN / "mockups/png").glob("*.png")):
        stem = max((s for s in htmls if png.stem.startswith(s + "-")), key=len, default=None)
        if stem and PRIVATE_IN_MOCKUP.search(htmls[stem].read_text(encoding="utf-8")):
            continue
        keep.append(png)
    return keep


def svg_ink(path: Path) -> str:
    fills = sorted(set(re.findall(r'fill="(#[0-9A-Fa-f]{3,8})"', path.read_text(encoding="utf-8"))))
    return ", ".join(f"`{f}`" for f in fills) if fills else "no fixed ink"


def build_assets(brand: str, icons_json: dict) -> list[dict]:
    mark_rows = {r[0]: r[1] for r in table_rows(section(brand, "Mark"))[1:]}

    def use_for(name: str) -> str:
        for key, use in mark_rows.items():
            patterns = [p.strip(" `").removeprefix("logo/") for p in key.split(",")]
            if any(fnmatch.fnmatch(name, p) for p in patterns):
                return use
        return ""

    logos = sorted((DESIGN / "brand/logo").glob("*.svg"))
    app_icons = sorted((DESIGN / "brand/icon").glob("*.svg"))
    icons = sorted((DESIGN / "dist/web/icons").glob("*.svg"))
    actions = icons_json["actions"]

    def native(v) -> str:
        if isinstance(v, dict):
            if "custom" in v:
                return f"custom `{v['custom']}`"
            return f"`{v['name']}` U+{v['glyph']}"
        return f"`{v}`"

    icon_table = ["| File | English | Norsk | SF Symbol | Material Symbol | Segoe Fluent |", "|---|---|---|---|---|---|"]
    for p in icons:
        a = actions[p.stem]
        icon_table.append(f"| `{p.name}` | {a['en']} | {a['nb']} | {native(a['apple'])} | {native(a['material'])} | "
                          f"{native(a['windows'])} |")

    return [
        {
            "name": "Logos", "tile": "l",
            "files": [(p, p.name) for p in logos] + [(DESIGN / "brand/legibility.png", "legibility.png")],
            "readme": "\n".join([
                ("The mark, the wordmark and the lockups, copied from the brand files. Each SVG has a fixed ink "
                "(an `<img>` cannot recolour it); pick the file for the ground."),
                "",
                "| File | Ink | Use |",
                "|---|---|---|",
                *[f"| `{p.name}` | {svg_ink(p)} | {use_for(p.name)} |" for p in logos],
                "| `legibility.png` | | The mark and lockups at small sizes: the mark stays legible at 16 px. |",
                "",
                portable("**Rules**" + section(brand, "Mark").split("**Rules**", 1)[1]),
            ]),
        },
        {
            "name": "App icon", "tile": "m",
            "files": [(p, p.name) for p in app_icons],
            "readme": portable(section(brand, "App icon").split("- **Build:**")[0].rstrip()) + "\n\n"
                      "The platform exports (PNG sets, .ico, adaptive icon XML) are generated from these masters "
                      "in the repository and are not copied here.",
        },
        {
            "name": "Icons", "tile": "xs",
            "files": [(p, p.name) for p in icons],
            "readme": "\n".join([
                icons_json["$description"],
                "",
                ("Each SVG is one Material Symbols Rounded path (or a custom glyph) on the 960 grid, filled with "
                "`currentColor`, which an `<img>` draws in black: inline the path to colour it (`text` on chrome)."),
                "",
                *icon_table,
            ]),
        },
        {
            "name": "Mockups", "tile": "l",
            "files": [(p, p.name) for p in mockup_pngs()],
            "readme": "The key screens, rendered from the HTML mockups: phone (iOS idiom) and desktop (macOS idiom), "
                      "light and dark, some in Norwegian (`nb`) and high contrast (`hc`). File names read "
                      "`<screen>-<device>-<theme>`.",
        },
        {
            "name": "Social", "tile": "l",
            "files": [(DESIGN / "brand/social/social-preview.png", "social-preview.png"),
                      (DESIGN / "brand/social/social-preview.svg", "social-preview.svg")],
            "readme": "Link previews, 1280 × 640: the repository's social preview on GitHub, and chat apps.",
        },
    ]


# ---------- the cover ----------

def build_cover() -> str:
    return '''<!-- @dsCard height=288 -->
<div class="cv">
  <svg class="cv-art" width="960" height="288" viewBox="0 0 960 288" aria-hidden="true">
    <!--
      blocks: brass 208x224 (radius-lg), primary ink 240x160 bleeding right, brass-tint 360x64 bleeding down,
              uncertain 64x64 (radius-sm) as the one score hue, kept small
      arrangement: one tall brass slab with an ink slab beside it, a tint band under both, all right of x=480
      pattern: five staff lines (the staff token, 1 px) crossing the blocks: editorial, serif, hairlines not shadows,
               and a stave is what the brand writes on
      scales: sizes are space-16 (64) multiples; staff pitch space-3 (12); corners radius-lg, radius-sm
    -->
    <rect class="b-brass" x="512" y="-16" width="208" height="224" rx="16"/>
    <rect class="b-ink" x="736" y="48" width="240" height="160" rx="16"/>
    <rect class="b-tint" x="600" y="224" width="376" height="80" rx="16"/>
    <rect class="b-unc" x="512" y="224" width="64" height="64" rx="8"/>
    <g class="staff">
      <line x1="480" y1="104" x2="960" y2="104"/>
      <line x1="480" y1="116" x2="960" y2="116"/>
      <line x1="480" y1="128" x2="960" y2="128"/>
      <line x1="480" y1="140" x2="960" y2="140"/>
      <line x1="480" y1="152" x2="960" y2="152"/>
    </g>
  </svg>
  <div class="cv-text">
    <p class="cv-name">Brasscribe</p>
    <p class="cv-tag">Warm paper and ink, generous space, one serif for headings, and brass used sparingly.</p>
  </div>
</div>
<style>
  .cv { position: relative; width: 960px; height: 288px; background: var(--bg); overflow: hidden; }
  .cv-art { position: absolute; inset: 0; }
  .b-brass { fill: var(--brass); }
  .b-ink { fill: var(--primary); }
  .b-tint { fill: var(--brass-tint); }
  .b-unc { fill: var(--uncertain); }
  .staff line { stroke: var(--staff); stroke-width: 1; }
  .cv-text { position: absolute; left: 40px; bottom: 32px; max-width: 440px; }
  .cv-name { margin: 0; font-family: var(--font-display); font-size: 80px; line-height: 0.95; color: var(--text); }
  .cv-tag { margin: 16px 0 0; font-family: var(--font-text); font-size: 14px; line-height: 1.4; color: var(--text-muted); }
</style>
'''


# ---------- main ----------

def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DESIGN / "claude/out")
    args = ap.parse_args()
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    proj = out / "project"

    src = json.loads(read("tokens/tokens.json"))
    web_css = read("dist/web/brasscribe.css")
    system, brand, readme = read("system.md"), read("brand/brand.md"), read("README.md")
    icons_json = json.loads(read("tokens/icons.json"))

    tokens = build_tokens(src, web_css)
    write(proj / "tokens.json", json.dumps(tokens, indent=2, ensure_ascii=False) + "\n")
    write(proj / "README.md", build_readme(tokens, src, system, brand, readme, icons_json))
    write(proj / "components-on-each-platform.md", build_components_md(system))
    write(proj / "music-stand.md", build_music_stand(read("music-stand.md")))
    write(proj / "components/bundle.css", build_css(tokens, read("mockups/mockup.css")))

    rows = {r[0].strip("*"): r for r in table_rows(section(system, "5. Components"))[1:]}
    icons, mark = load_icons(), mark_path()
    for c in components(icons, mark):
        d = proj / "components" / c["name"]
        write(d / "preview.html", f'<!-- @dsCard group="{c["group"]}" height={c["height"]} -->\n{c["html"]}\n')
        write(d / "README.md", component_readme(c, rows))
    write(proj / "components/Cover/preview.html", build_cover())

    for f in ("InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf"):
        (proj / "fonts").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DESIGN / "brand/fonts" / f, proj / "fonts" / f)
    write(proj / "assets/Licences/OFL.txt", read("brand/fonts/OFL.txt"))
    write(proj / "assets/Licences/material-symbols-LICENSE.txt", read("brand/icons/material/LICENSE"))
    write(proj / "assets/Licences/README.md",
          "Instrument Serif is under the SIL Open Font License 1.1 (`OFL.txt`). The Material Symbols icons are under "
          "the Apache License 2.0 (`material-symbols-LICENSE.txt`).\n")

    file_map = []
    for g in build_assets(brand, icons_json):
        write(proj / "assets" / g["name"] / "README.md", g["readme"].rstrip("\n") + "\n")
        entries = []
        for p, name in g["files"]:
            dest = proj / "assets" / g["name"] / name
            shutil.copyfile(p, dest)
            entries.append({"name": name, "source": str(p.relative_to(DESIGN.parent)), "size": p.stat().st_size,
                            "type": MEDIA_TYPES[p.suffix]})
        file_map.append({"group": g["name"], "tile": g["tile"], "files": entries})
    write(out / "assets.json", json.dumps({"groups": file_map}, indent=2) + "\n")

    n = sum(len(g["files"]) for g in file_map)
    print(f"{out}: {len(tokens['color']['tokens'])} colours x {len(MODES)} themes, "
          f"{sum(len(g['styles']) for g in tokens['type']['groups'])} type styles, "
          f"{len(components(icons, mark))} components, {n} assets")


if __name__ == "__main__":
    main()
