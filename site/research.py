"""The research pages' numbers, figures and shared parts. Standard library only; used by site/build.py.

No number is typed into a research page. A page names the measurement and the build prints it:

  {{data <key> [format]}}           one number, e.g. {{data brass/quant-urmp/beat_this.position_acc pct}}
                                    (formats: f1 f2 f3 decimals, pct, int, sec seconds, gb gigabytes)
  {{span <key> <key> … [format]}}   the lowest and the highest of several, e.g. 0.24–0.27
  {{holds <key> <op> <key|number>}} prints nothing; the build fails when the comparison is false, so a
                                    sentence such as "under half" cannot outlive the numbers it rests on
  {{chart <figure>}}                an interactive figure with its data table (site/shared/charts.js draws it)
  {{pipeline <figure>}}             a diagram of stages
  {{part <name>}}                   site/shared/research/<lang>/<name>.html, shared by the products' pages

A key is <target>/<suite>/<metric> in eval/baselines.json (target: brass or fretted), or
m/<table>/<field> in site/shared/research/measured/measured.toml: numbers that were measured once and exist
only in prose under docs/, each with where it came from, or p/<suite>/pieces and p/<suite>/notes: the
size of an eval set, counted by site/shared/research/per_piece.py, or c/<model>/<backend>.<field> in
convert/reports/<model>.json (a converted model's benchmark; s_per_min and peak_gb are derived from its
rtf and peak_rss_mb). per_piece.py also writes the value of every piece behind a gated mean
(site/shared/research/measured/per-piece.json), which the charts show.

The figures themselves are described in site/shared/research/figures.py.
"""

from __future__ import annotations

import html
import json
import operator
import runpy
import sys
import tomllib
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
SHARED = SITE / "shared" / "research"
MACROS = ("span", "holds", "chart", "pipeline", "part")  # and {{data <key>}}, which site/build.py passes on
FORMATS = ("f1", "f2", "f3", "pct", "int", "sec", "gb")
NBSP = chr(0xA0)  # between a number and its unit, and between thousands in Norwegian
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}
WORDS = {
    "en": {"figure": "Figure", "table": "Data table", "measure": "Measure", "n": "Measured on", "range": "lowest–highest",
           "source": "Source"},
    "nb": {"figure": "Figur", "table": "Datatabell", "measure": "Mål", "n": "Målt på", "range": "laveste–høyeste",
           "source": "Kilde"},
}


class Numbers:
    def __init__(self) -> None:
        base = json.loads((ROOT / "eval" / "baselines.json").read_text())
        self.tolerance = base["tolerance"]
        self.targets = {t: {s: v["metrics"] for s, v in body["suites"].items()} for t, body in base["targets"].items()}
        self.measured = tomllib.loads((SHARED / "measured" / "measured.toml").read_text())
        self.pieces = json.loads((SHARED / "measured" / "per-piece.json").read_text())["suites"]
        self.figures = runpy.run_path(str(SHARED / "figures.py"))
        self.converted = {f.stem: json.loads(f.read_text()) for f in sorted((ROOT / "convert" / "reports").glob("*.json"))}

    def get(self, key: str) -> float:
        head, _, rest = key.partition("/")
        group, _, name = rest.partition("/")
        try:
            if head == "c":
                if name == "threshold_f1":  # the parity a conversion must reach before the apps use it
                    return float(self.converted[group][name])
                backend, _, field = name.rpartition(".")
                run = self.converted[group]["benchmarks"][backend]
                return {"s_per_min": lambda: run["rtf"] * 60, "peak_gb": lambda: run["peak_rss_mb"] / 1024}.get(field, lambda: run[field])()
            value = {"m": self.measured, "p": self.pieces}[head][group][name] if head in ("m", "p") else self.targets[head][group][name]
        except KeyError:
            sys.exit(f"research: no measurement '{key}'")
        return float(value["value"] if isinstance(value, dict) else value)

    def spread(self, key: str) -> list[float] | None:
        """The per-piece values behind a gated mean, unless the mean has moved since they were made."""
        head, _, rest = key.partition("/")
        suite, _, name = rest.partition("/")
        values = self.pieces.get(suite, {}).get(name) if head == "brass" else None
        if not isinstance(values, list):
            return None
        if abs(sum(values) / len(values) - self.get(key)) > self.tolerance:
            print(f"research: per-piece values of {key} are stale; run site/shared/research/per_piece.py", file=sys.stderr)
            return None
        return values


_numbers: Numbers | None = None


def numbers() -> Numbers:
    global _numbers
    _numbers = _numbers or Numbers()
    return _numbers


def rounded(value: float, decimals: int) -> str:
    """Half up on the number as it is stored: 0.305 is 0.31, where float formatting gives 0.30."""
    return str(Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


def fmt(value: float, how: str, lang: str) -> str:
    if how == "pct":
        text = f"{rounded(round(value * 100, 6), 0)}{NBSP}%"
    elif how in ("sec", "gb"):  # a duration or a size: as many decimals as its magnitude needs
        text = f"{rounded(value, 2 if value < 1 else 1 if value < 10 else 0)}{NBSP}{'s' if how == 'sec' else 'GB'}"
    elif how == "int":
        text = f"{round(value):,}".replace(",", NBSP if lang == "nb" else ",")
    else:
        text = rounded(value, int(how[1:]))
    return text.replace(".", ",") if lang == "nb" else text


def pick(text, lang: str) -> str:
    """Figures give their words as (English, Norwegian)."""
    return text if isinstance(text, str) else text[0 if lang == "en" else 1]


def fill(text, lang: str, how: str) -> str:
    """A title or caption with measurements in it: 'finds {brass/…/x} of the notes' (optionally {key|pct})."""
    out, rest = [], pick(text, lang)
    while "{" in rest:
        before, _, tail = rest.partition("{")
        key, _, rest = tail.partition("}")
        key, _, how_here = key.partition("|")
        out += [before, fmt(numbers().get(key), how_here or how, lang)]
    return "".join(out) + rest


def check(rule: list[str], where: str) -> None:
    key, op, other = rule
    left = numbers().get(key)
    right = numbers().get(other) if "/" in other else float(other)
    if not OPS[op](left, right):
        sys.exit(f"research: {where} says '{key} {op} {other}', but it is {left} against {right}. "
                 "The numbers have moved: rewrite the sentence or the figure's title, then the rule.")


# Macros -----------------------------------------------------------------------------------------

def macro(page, name: str, words: list[str], args: dict[str, str]) -> str:
    lang = page.lang
    if name in ("data", "span"):
        how = words.pop() if words[-1] in FORMATS else "f2"
        values = [numbers().get(w) for w in words]
        if name == "data":
            return fmt(values[0], how, lang)
        low, high = fmt(min(values), how, lang), fmt(max(values), how, lang)
        return low if low == high else f"{low.replace(NBSP + '%', '')}–{high}"
    if name == "holds":
        check(words, page.dir or "the front page")
        return ""
    if name == "part":
        return page.macros((SHARED / lang / f"{words[0]}.html").read_text().rstrip())
    page.figures = getattr(page, "figures", 0) + 1
    spec = numbers().figures["FIGURES"].get(words[0])
    if spec is None:
        sys.exit(f"{page.dir}: no figure '{words[0]}' in site/shared/research/figures.py")
    for rule in spec.get("holds", []):
        check(rule.split(), f"figure '{words[0]}'")
    return pipeline(spec, words[0], page) if name == "pipeline" else chart(spec, words[0], page)


# Charts -----------------------------------------------------------------------------------------

def chart(spec: dict, name: str, page) -> str:
    lang, w, num, e = page.lang, WORDS[page.lang], numbers(), html.escape
    series = [pick(s, lang) for s in spec["series"]]
    views = []
    for view in spec["views"]:
        how, top, rows = view.get("format", spec.get("format", "f2")), view.get("max", spec.get("max", 1)), []
        if top == "auto":  # the first round number at or over the largest value, so every bar fits and the ticks are whole
            largest = max(num.get(k) for row in view["rows"] for k in row["keys"] if k)
            top = next(n for n in (1, 2, 4, 8, 12, 16, 20, 24, 32, 40, 60, 80, 120, 160, 240, 320, 480, 960) if n >= largest)
        for row in view["rows"]:
            cells = []
            for key in row["keys"]:
                if key is None:
                    cells.append(None)
                    continue
                value, pieces = num.get(key), num.spread(key)
                cell = {"v": value, "t": fmt(value, how, lang)}
                if pieces:
                    cell |= {"p": pieces, "lo": fmt(min(pieces), how, lang), "hi": fmt(max(pieces), how, lang)}
                cells.append(cell)
            rows.append({"l": pick(row["label"], lang), "n": fill(row.get("n", view.get("n", "")), lang, "int"), "c": cells})
        tick = "int" if how in ("sec", "gb") else "pct" if how == "pct" else "f2"
        views.append({"l": pick(view["label"], lang), "note": fill(view.get("note", ""), lang, how), "rows": rows, "max": top,
                      "axis": pick(view.get("axis", spec.get("axis")), lang),
                      "ticks": [{"v": top * i / 4, "t": fmt(top * i / 4, tick, lang)} for i in range(5)]})
    how = spec.get("format", "f2")
    data = {"series": series, "views": views,
            "viewLabel": pick(spec.get("view_label", ""), lang),
            "words": {"range": w["range"]}}

    tables = []
    spread = any(c and "p" in c for v in views for r in v["rows"] for c in r["c"])
    for view in views:
        sizes = {row["n"] for row in view["rows"]}
        shared = sizes.pop() if len(sizes) == 1 else None  # one answer for every row goes under the caption, not in a column
        head = [f'<th scope="col">{w["measure"]}</th>']
        for name in series:
            head.append(f'<th scope="col" class="num">{e(name)}</th>')
            if spread:
                head.append(f'<th scope="col" class="num">{w["range"]}</th>')
        if shared is None:
            head.append(f'<th scope="col">{w["n"]}</th>')
        body = []
        for row in view["rows"]:
            cells = [f'<th scope="row">{e(row["l"])}</th>']
            for c in row["c"]:
                cells.append(f'<td class="num">{c["t"] if c else "–"}</td>')
                if spread:
                    cells.append(f'<td class="num">{c["lo"]}–{c["hi"]}</td>' if c and "p" in c else "<td></td>")
            if shared is None:
                cells.append(f'<td>{e(row["n"])}</td>')
            body.append(f'<tr>{"".join(cells)}</tr>')
        note = " ".join(x for x in (view["note"], f'{w["n"]}: {e(shared)}.' if shared else "") if x)
        caption = view["l"] + (f'<span class="src">{note}</span>' if note else "")
        tables.append(f'<div class="table-scroll" tabindex="0" role="region" aria-label="{e(w["table"])}: {e(view["l"])}">\n<table>\n'
                      f'<caption>{caption}</caption>\n<thead><tr>{"".join(head)}</tr></thead>\n'
                      f'<tbody>\n{chr(10).join(body)}\n</tbody>\n</table>\n</div>')
    source = fill(spec["source"], lang, how)
    return (f'<figure class="chart" id="fig-{name}" aria-labelledby="fig-{name}-title" data-chart data-brand="{page.product.id}">\n'
            f'<p class="chart-title" id="fig-{name}-title">{fill(spec["title"], lang, how)}</p>\n'
            f'<p class="chart-sub">{fill(spec["sub"], lang, how)}</p>\n'
            f'<div class="chart-plot" hidden></div>\n'
            f'<details class="chart-data" open>\n<summary>{w["table"]}</summary>\n{chr(10).join(tables)}\n</details>\n'
            f'<figcaption><b>{w["figure"]} {page.figures}.</b> {fill(spec["caption"], lang, how)} <span class="src">{w["source"]}: {source}</span></figcaption>\n'
            f'<script type="application/json">{json.dumps(data, ensure_ascii=False).replace("</", "<\\/")}</script>\n</figure>')


# Stage diagrams ---------------------------------------------------------------------------------

def pipeline(spec: dict, name: str, page) -> str:
    """Rows of one box or two side by side; each box is (kind, title, lines): kind is model, rule or human."""
    lang, w, e = page.lang, WORDS[page.lang], html.escape
    out, y, above = [], 8, None
    for row in spec["rows"]:
        height = 28 + 16 * max(len(pick(box[2], lang)) for box in row)
        xs = [(10, 420)] if len(row) == 1 else [(10, 205), (225, 205)]
        for (kind, title, lines), (x, width) in zip(row, xs):
            cls = {"model": "model", "human": "human"}.get(kind, "plain")
            out.append(f'<rect class="box {cls}" x="{x}" y="{y}" width="{width}" height="{height}" rx="8"/>'
                       f'<text class="t" x="{x + 12}" y="{y + 19}">{e(pick(title, lang))}</text>')
            for i, line in enumerate(pick(lines, lang)):
                out.append(f'<text class="s" x="{x + 12}" y="{y + 36 + 16 * i}">{e(line)}</text>')
        if above is not None:
            centres = [220] if len(row) == 1 and above == 1 else [112, 327]
            for cx in centres:
                out.append(f'<line class="arrow" x1="{cx}" y1="{y - 20}" x2="{cx}" y2="{y - 7}"/>'
                           f'<path class="head" d="M{cx - 5} {y - 8} L{cx + 5} {y - 8} L{cx} {y} Z"/>')
        above, y = len(row), y + height + 20
    legend = spec["legend"]
    return (f'<figure id="fig-{name}">\n'
            f'<svg class="diagram diagram-pipeline" viewBox="0 0 440 {y - 12}" role="img" aria-labelledby="{name}-title {name}-desc" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{name}-title">{e(pick(spec["title"], lang))}</title><desc id="{name}-desc">{e(pick(spec["desc"], lang))}</desc>{"".join(out)}</svg>\n'
            f'<ul class="legend" aria-hidden="true">\n<li><i class="model"></i>{pick(legend[0], lang)}</li>\n<li><i></i>{pick(legend[1], lang)}</li>\n'
            f'<li><i class="human"></i>{pick(legend[2], lang)}</li>\n</ul>\n'
            f'<figcaption><b>{w["figure"]} {page.figures}.</b> {pick(spec["caption"], lang)}</figcaption>\n</figure>')
