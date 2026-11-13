"""The research pages' numbers, figures and shared parts. Standard library only; used by site/build.py.

No number is typed into a research page. A page names the measurement and the build prints it:

  {{data <key> [format]}}           one number, e.g. {{data brass/quant-urmp/beat_this.position_acc pct}}
                                    (formats: f1 f2 f3 decimals, pct, int, sec seconds, gb gigabytes)
  {{span <key> <key> … [format]}}   the lowest and the highest of several, e.g. 0.24–0.27
  {{holds <key> <op> <key|number>}} prints nothing; the build fails when the comparison is false, so a
                                    sentence such as "under half" cannot outlive the numbers it rests on
  {{chart <figure>}}                an interactive figure with its data table (site/shared/charts.js draws it)
  {{pipeline <figure>}}             a diagram of stages
  {{part <name>}}                   site/shared/research/<name>.html, shared by the products' pages

A page is written as every page of the site: its structure once, its words by key in <page>.en.toml and
<page>.nb.toml. A number is printed the way its language writes it (0.66, 0,66), in a sentence and in a table
cell alike. What the research pages share has its words in site/shared/research/words.en.toml and words.nb.toml:
[chart] what every figure says, [figure.<name>] the words of one figure, [measure.<name>] those of a shared part.

A key is <target>/<suite>/<metric> in eval/baselines.json (target: brass or fretted), or
m/<table>/<field> in site/shared/research/measured/measured.toml: numbers that were measured once and exist
only in prose under docs/, each with where it came from, or p/<suite>/pieces and p/<suite>/notes: the
size of an eval set, counted by site/shared/research/per_piece.py, or c/<model>/<backend>.<field> in
convert/reports/<model>.json (a converted model's benchmark; s_per_min and peak_gb are derived from its
rtf and peak_rss_mb). per_piece.py also writes the value of every piece behind a gated mean
(site/shared/research/measured/per-piece.json), which the charts show; <key>@min and <key>@max are the
lowest and the highest of them.

The figures themselves are described in site/shared/research/figures.py, which names their words by key.

A paper follows the conventions of its field, and the build holds it to them:

  {{cite <key> …}}                  [3], numbered in the order of first citation; the keys are the tables of
                                    site/shared/research/references.toml. An unknown key fails the build, and so
                                    does an entry there that no paper cites.
  {{references}}                    the reference list of the page: what it cited, in that order
  {{ref fig:<name>}}, {{ref table:<name>}}, {{ref eq:<name>}}
                                    "Figure 3", "Table 2", "(1)", linked. Figures, tables and equations are
                                    numbered separately, in the order they appear on the page.
  {{label table:<name>}}, {{label eq:<name>}}
                                    the number where the table's caption or the equation stands (a figure has its
                                    number from {{chart}} or {{pipeline}}). A figure or a table that the text has
                                    not referred to before it appears fails the build.
  {{built}}                         the date and the commit of the checkout the page was built from
  {{figuretables}}                  the data tables of the figures above it, for an appendix: in print a figure is its
                                    plot and caption, and its table stands there

After the pages are written, finish() checks each paper's abstract for its length in both languages, and that
every word of words.<lang>.toml is used.
"""

from __future__ import annotations

import html
import json
import operator
import random
import re
import statistics
import subprocess
import runpy
import sys
import tomllib
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
SHARED = SITE / "shared" / "research"
MACROS = ("span", "holds", "chart", "pipeline", "part", "cite", "references", "ref", "label", "built", "figuretables")  # and {{data <key>}}, which site/build.py passes on
FORMATS = ("f1", "f2", "f3", "pct", "int", "sec", "gb")
LANGS = ("en", "nb")
NBSP = chr(0xA0)  # between a number and its unit, and between thousands in Norwegian
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def script_guard() -> None:
    """charts.js keeps a chart's parts on the chart object, beside its methods. A part named as a method hides the
    method (a legend kept as `key` once stopped every arrow key), so the build refuses such a name."""
    text = (SITE / "shared" / "charts.js").read_text()
    clash = set(re.findall(r"Chart\.prototype\.(\w+)\s*=", text)) & set(re.findall(r"\bthis\.(\w+)\s*=[^=]", text))
    if clash:
        sys.exit(f"research: site/shared/charts.js assigns this.{sorted(clash)[0]}, which hides the method of that name")


class Numbers:
    def __init__(self) -> None:
        script_guard()
        base = json.loads((ROOT / "eval" / "baselines.json").read_text())
        self.tolerance = base["tolerance"]
        self.targets = {t: {s: v["metrics"] for s, v in body["suites"].items()} for t, body in base["targets"].items()}
        self.measured = tomllib.loads((SHARED / "measured" / "measured.toml").read_text())
        self.pieces = json.loads((SHARED / "measured" / "per-piece.json").read_text())["suites"]
        self.figures = runpy.run_path(str(SHARED / "figures.py"), {"T": T})
        self.converted = {f.stem: json.loads(f.read_text()) for f in sorted((ROOT / "convert" / "reports").glob("*.json"))}

    def get(self, key: str) -> float:
        if "@" in key:  # of the pieces behind a mean: @min @max @sd @lo @hi @n @mean, or @0.60-0.75: how many lie in a range
            key, _, end = key.rpartition("@")
            head, _, rest = key.partition("/")
            suite, _, name = rest.partition("/")
            # p/<suite>/<name>: per-piece values that have no gated mean (their mean is <key>@mean)
            pieces = self.pieces.get(suite, {}).get(name) if head == "p" else self.spread(key)
            if not isinstance(pieces, list):
                pieces = None
            if pieces is None:
                sys.exit(f"research: no per-piece values for '{key}'")
            if end in ("lo", "hi"):
                return interval(pieces)[end == "hi"]
            if "-" in end:
                low, _, high = end.partition("-")
                return sum(float(low) <= value <= float(high) for value in pieces)
            return {"min": min, "max": max, "sd": statistics.stdev, "n": len, "mean": statistics.fmean}[end](pieces)
        head, _, rest = key.partition("/")
        group, _, name = rest.partition("/")
        try:
            if head == "c":
                if name == "threshold_f1":  # the parity a conversion must reach before the apps use it
                    return float(self.converted[group][name])
                backend, _, field = name.rpartition(".")
                if field == "parity":  # as convert/summarize.py: the lowest of the F1 scores against the reference framework
                    entry = self.converted[group]["parity"][backend]
                    return min(entry[k]["f1"] for k in ("note_f1", "beat_f1", "downbeat_f1", "swift_f0_note_f1", "basic_pitch_note_f1") if k in entry)
                run = self.converted[group]["benchmarks"][backend]
                return {"s_per_min": lambda: run["rtf"] * 60, "peak_gb": lambda: run["peak_rss_mb"] / 1024}.get(field, lambda: run[field])()
            value = {"m": self.measured, "p": self.pieces}[head][group][name] if head in ("m", "p") else self.targets[head][group][name]
        except KeyError:
            sys.exit(f"research: no measurement '{key}'")
        if isinstance(value, list):  # per-piece values without a gated mean: the key is their mean
            return statistics.fmean(value)
        return float(value["value"] if isinstance(value, dict) else value)

    def spread(self, key: str) -> list[float] | None:
        """The per-piece values behind a gated mean, unless the mean has moved since they were made."""
        head, _, rest = key.partition("/")
        suite, _, name = rest.partition("/")
        if head == "p":
            values = self.pieces.get(suite, {}).get(name)
            return values if isinstance(values, list) else None
        values = self.pieces.get(suite, {}).get(name) if head in self.targets else None
        if not isinstance(values, list):
            return None
        if abs(sum(values) / len(values) - self.get(key)) > self.tolerance:
            sys.exit(f"research: the per-piece values of {key} no longer average to its baseline, so the figures would show "
                     "dots that are not behind the mean. Run site/shared/research/per_piece.py on a machine with the eval data.")
        return values


def interval(pieces: list[float]) -> tuple[float, float]:
    """A 95 % confidence interval of the mean over pieces: percentile bootstrap, 10,000 resamples, a fixed seed."""
    key = tuple(pieces)
    if key not in interval.__dict__.setdefault("made", {}):
        draw = random.Random(20261113)
        means = sorted(statistics.fmean(draw.choices(pieces, k=len(pieces))) for _ in range(10_000))
        interval.made[key] = (means[249], means[9749])
    return interval.made[key]


_numbers: Numbers | None = None


def numbers() -> Numbers:
    global _numbers
    _numbers = _numbers or Numbers()
    return _numbers


def rounded(value: float, decimals: int) -> str:
    """Half up on the number as it is stored: 0.305 is 0.31, where float formatting gives 0.30."""
    return str(Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


def fmt(value: float, how: str, lang: str) -> str:
    if how == "pct":  # under 10 %, one decimal where there is one: 0.4 % is not 0 %
        percent = round(value * 100, 6)
        text = f"{rounded(percent, 1 if 0 < percent < 10 and percent % 1 else 0)}{NBSP}%"
    elif how in ("sec", "gb"):  # a duration or a size: as many decimals as its magnitude needs
        text = f"{rounded(value, 2 if value < 1 else 1 if value < 10 else 0)}{NBSP}{'s' if how == 'sec' else 'GB'}"
    elif how == "int":
        text = f"{round(value):,}".replace(",", NBSP if lang == "nb" else ",")
    else:
        text = rounded(value, int(how[1:]))
    return text.replace(".", ",") if lang == "nb" else text


class T:
    """The words of a figure: a key under [figure] of words.en.toml and words.nb.toml, and what fills its %1, %2 …"""

    def __init__(self, key: str, *values) -> None:
        self.key, self.values = key, values


SAID: set[str] = set()


def table(lang: str) -> dict:
    """The research pages' own words, by key: [chart], [figure.<name>] and [measure.<name>] of words.<lang>.toml."""
    if "made" not in table.__dict__:
        def flat(nested: dict, prefix: str = "") -> dict:
            out = {}
            for key, value in nested.items():
                out.update(flat(value, f"{prefix}{key}.") if isinstance(value, dict) else {prefix + key: value})
            return out
        table.made = {each: flat(tomllib.loads((SHARED / f"words.{each}.toml").read_text())) for each in LANGS}
        differ = set(table.made["en"]) ^ set(table.made["nb"])
        if differ:
            sys.exit(f"research: words.en.toml and words.nb.toml differ in: {', '.join(sorted(differ))}")
    return table.made[lang]


def pick(text, lang: str):
    """A figure's words in the language being written; a name that is the same in both is given as it is."""
    if not isinstance(text, T):
        return text
    if "figure." + text.key not in table(lang):
        sys.exit(f"research: figures.py names the words '{text.key}', which words.{lang}.toml does not have under [figure]")
    SAID.add("figure." + text.key)
    said = table(lang)["figure." + text.key]
    for i in range(len(text.values), 0, -1):
        said = said.replace(f"%{i}", str(pick(text.values[i - 1], lang)))
    return said


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
    paper = numbering(page)
    if name == "part":
        made = page.macros((SHARED / f"{words[0]}.html").read_text().rstrip())
        page.lang = lang  # the page writes each macro in both languages, and is back at the first when it has
        return made
    if name == "cite":
        return "[" + ", ".join(f'<a href="#ref-{key}">{paper["cited"].index(key) + 1}</a>' for key in words) + "]"
    if name == "references":
        items = []
        for key in paper["cited"]:
            entry = references()[key]
            note = entry.get("note_" + lang, entry.get("note", ""))
            items.append(f'<li id="ref-{key}">{entry["text"]}{" " + note if note else ""}</li>')
        return '<ol class="refs">\n' + "\n".join(items) + "\n</ol>"
    if name == "built":
        return built(lang)
    if name == "figuretables":  # the data tables of every figure so far, for the appendix that only print shows
        return "\n".join(f'<h3>{table(lang)["chart.fig"]}{NBSP}{number}</h3>\n' + "\n".join(tables) for number, tables in paper["tables"])
    if name in ("ref", "label"):
        kind, _, what = words[0].partition(":")
        number = paper[kind].get(what)
        if number is None:
            sys.exit(f"{page.dir}: {{{{{name} {words[0]}}}}} names nothing that the page shows")
        if name == "ref":
            if kind == "eq":
                return f'<a href="#eq-{what}">({number})</a>'
            return f'<a href="#{kind}-{what}">{table(lang)["chart." + kind]}{NBSP}{number}</a>'
        return f"({number})" if kind == "eq" else f"{table(lang)["chart." + kind]}{NBSP}{number}"
    page.figures = paper["fig"][words[0]]
    spec = numbers().figures["FIGURES"].get(words[0])
    if spec is None:
        sys.exit(f"{page.dir}: no figure '{words[0]}' in site/shared/research/figures.py")
    for rule in spec.get("holds", []):
        check(rule.split(), f"figure '{words[0]}'")
    return pipeline(spec, words[0], page) if name == "pipeline" else chart(spec, words[0], page)


# The conventions of a paper ------------------------------------------------------------------------

CITED: set[str] = set()


def references() -> dict:
    if "made" not in references.__dict__:
        references.made = tomllib.loads((SHARED / "references.toml").read_text())
    return references.made


def numbering(page) -> dict:
    """What a paper numbers, read from its whole text in the language being written before any macro runs: figures,
    tables and equations, each kind in the order it appears, and its sources in the order they are first cited. The
    build writes a page's figures before its words, so the order cannot be taken from the order the macros run in."""
    papers = page.__dict__.get("papers")
    if papers is None:
        papers = page.papers = {}
        for lang in LANGS:  # the shared parts' words, beside the page's own
            page.table[lang] = {**{key: said for key, said in table(lang).items() if key.startswith("measure.")}, **page.table[lang]}
    if page.lang not in papers:
        body = page.body if isinstance(page.body, str) else page.body["en"]
        for _ in range(3):  # a part may hold a figure or an equation
            body = re.sub(r"\{\{part ([\w-]+)\}\}", lambda m: (SHARED / f"{m.group(1)}.html").read_text(), body)
        # Each element's words stand where the element does.
        body = re.sub(r'<(\w+)[^<>]*? data-t="([^"]+)"[^<>]*></\1>', lambda m: str(page.table[page.lang].get(m.group(2), "")), body)
        paper = papers[page.lang] = {"fig": {}, "table": {}, "eq": {}, "cited": [], "tables": []}
        strict, seen = "{{references}}" in body, set()
        for kind, rest in re.findall(r"\{\{(chart|pipeline|label|ref|cite) ([^{}]+)\}\}", body):
            if kind == "cite":
                for key in rest.split():
                    if key not in references():
                        sys.exit(f"{page.dir}: {{{{cite {key}}}}} names no entry of site/shared/research/references.toml")
                    if key not in paper["cited"]:
                        paper["cited"].append(key)
                    CITED.add(key)
                continue
            if kind == "ref":
                seen.add(rest.strip())
                continue
            kind, _, what = (rest if kind == "label" else "fig:" + rest).strip().partition(":")
            if strict and kind in ("fig", "table") and f"{kind}:{what}" not in seen and what not in paper[kind]:
                sys.exit(f"{page.dir} ({page.lang}): {'figure' if kind == 'fig' else 'table'} '{what}' appears before the text "
                         f"refers to it with {{{{ref {kind}:{what}}}}}")
            paper[kind].setdefault(what, len(paper[kind]) + 1)
    return papers[page.lang]


def built(lang: str) -> str:
    """The date and commit of the checkout: what the numbers on the page were read from."""
    if "made" not in built.__dict__:
        run = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%cs %h"], capture_output=True, text=True)
        built.made = run.stdout.split() if run.returncode == 0 and run.stdout.strip() else None
    if built.made is None:
        sys.exit("research: {{built}} needs the git history of the checkout (the date and the commit of HEAD)")
    year, month, day = built.made[0].split("-")
    months = {"en": "January February March April May June July August September October November December",
              "nb": "januar februar mars april mai juni juli august september oktober november desember"}[lang].split()
    date = f"{int(day)} {months[int(month) - 1]} {year}" if lang == "en" else f"{int(day)}. {months[int(month) - 1]} {year}"
    return f'<time datetime="{built.made[0]}">{date}</time>, {"commit" if lang == "en" else "innsjekking"} <code>{built.made[1]}</code>'


def finish(out: Path) -> None:
    """What can only be checked when every page is written: unused references and words, and the length of each abstract."""
    unused = sorted(set(references()) - CITED)
    if unused:
        sys.exit(f"research: no paper cites {', '.join(unused)}; cite them or take them out of site/shared/research/references.toml")
    parts = "".join(part.read_text() for part in sorted(SHARED.glob("*.html")))
    idle = sorted(key for key in table("en") if (key.startswith("figure.") and key not in SAID)
                  or (key.startswith("measure.") and f'"{key}"' not in parts))
    if idle:
        sys.exit(f"research: words that no figure or shared part uses, in words.en.toml and words.nb.toml: {', '.join(idle)}")
    for page in sorted(out.rglob("index.html")):
        text = page.read_text()
        found = re.search(r'<p class="abstract-text"(?: data-t="([^"]+)")?>(.*?)</p>', text, re.S)
        if '<article class="paper"' in text and not found:
            sys.exit(f"research: {page.relative_to(out)} is a paper without an abstract (<p class=\"abstract-text\">)")
        if found:
            abstracts = {"en": found.group(2)}
            if found.group(1):
                abstracts["nb"] = json.loads((page.parent / "nb.json").read_text())["t"][found.group(1)]
            for lang, abstract in abstracts.items():
                count = len(re.sub(r"<[^>]+>", " ", abstract).split())
                if not 150 <= count <= 250:
                    sys.exit(f"research: the abstract of {page.relative_to(out)} ({lang}) is {count} words; a paper's abstract is 150 to 250")


# Charts -----------------------------------------------------------------------------------------

def whole(made: str, name: str) -> str:
    """A figure with a measurement's name still in it has words that were never filled in."""
    left = re.search(r"\{[a-z]+/[^{}\s]*\}", made)
    if left:
        sys.exit(f"research: figure '{name}' prints {left.group(0)} as it stands; that text is not filled in")
    return made


def chart_words(lang: str) -> dict:
    return {key.removeprefix("chart."): said for key, said in table(lang).items() if key.startswith("chart.")}


def chart(spec: dict, name: str, page) -> str:
    lang, w, num, e = page.lang, chart_words(page.lang), numbers(), html.escape
    views = []
    for view in spec["views"]:
        how, top, rows = view.get("format", spec.get("format", "f2")), view.get("max", spec.get("max", 1)), []
        log = view.get("scale") == "log"  # (lowest, highest) in powers of ten: for values that span several of them
        if top == "auto":  # the first round number at or over the largest value, so every bar fits and the ticks are whole
            largest = max(num.get(k) for row in view["rows"] for k in row["keys"] if k)
            top = next(n for n in (1, 2, 4, 8, 12, 16, 20, 24, 32, 40, 60, 80, 120, 160, 240, 320, 480, 960) if n >= largest)
        for row in view["rows"]:
            cells = []
            for key in row["keys"]:
                if key is None:
                    cells.append(None)
                    continue
                value, pieces = num.get(key), num.spread(key) if spec.get("spread", True) else None
                cell = {"v": value, "t": fmt(value, how, lang)}
                if pieces:
                    low, high = interval(pieces)
                    cell |= {"p": pieces, "lo": fmt(min(pieces), how, lang), "hi": fmt(max(pieces), how, lang), "ci": [low, high],
                             "sd": fmt(statistics.stdev(pieces), how, lang),
                             "cit": f"{fmt(low, how, lang).replace(NBSP + '%', '')}–{fmt(high, how, lang)}"}
                cells.append(cell)
            rows.append({"l": pick(row["label"], lang), "n": fill(row.get("n", view.get("n", "")), lang, "int"), "c": cells})
        series = [pick(s, lang) for s in view.get("series", spec["series"])]  # a view may compare other things than its neighbours
        tick = "int" if how in ("sec", "gb") else "pct" if how == "pct" else "f2"
        ticks = [{"v": top * i / 4, "t": fmt(top * i / 4, tick, lang)} for i in range(5)]
        if log:
            low, top = view["log"]
            ticks = [{"v": 10.0 ** e, "t": fmt(10.0 ** e, how, lang)} for e in range(low, top + 1)]
            low, top = 10.0 ** low, 10.0 ** top
        sizes = {row["n"] for row in rows}
        mark = view.get("mark", spec.get("mark"))
        views.append({"l": pick(view["label"], lang), "note": fill(view.get("note", ""), lang, how), "rows": rows, "max": top,
                      "min": low if log else 0, "log": log, "n": sizes.pop() if len(sizes) == 1 else None, "s": series,
                      "mark": {"v": num.get(mark[0]), "t": fill(mark[1], lang, how)} if mark else None,
                      "axis": fill(view.get("axis", spec.get("axis")), lang, how), "ticks": ticks})
    how = spec.get("format", "f2")
    data = {"views": views,
            "viewLabel": pick(spec.get("view_label", ""), lang),
            "words": {"range": w["range"], "hint": w["hint"], "sd": w["sd"], "ci": w["ci"]}}

    tables = []
    spread = any(c and "p" in c for v in views for r in v["rows"] for c in r["c"])
    for view in views:
        shared = view["n"]  # one answer for every row goes under the caption, not in a column
        head = [f'<th scope="col">{w["measure"]}</th>']
        for label in view["s"]:
            head.append(f'<th scope="col" class="num">{e(label)}</th>')
            if spread:
                head += [f'<th scope="col" class="num">{w["sd"]}</th>', f'<th scope="col" class="num">{w["ci"]}</th>']
        if shared is None:
            head.append(f'<th scope="col">{w["n"]}</th>')
        body = []
        for row in view["rows"]:
            cells = [f'<th scope="row">{e(row["l"])}</th>']
            for c in row["c"]:
                cells.append(f'<td class="num">{c["t"] if c else "–"}</td>')
                if spread:
                    cells.append(f'<td class="num">{c["sd"]}</td><td class="num">{c["cit"]}</td>' if c and "p" in c else "<td></td><td></td>")
            if shared is None:
                cells.append(f'<td>{e(row["n"])}</td>')
            body.append(f'<tr>{"".join(cells)}</tr>')
        note = " ".join(x for x in (view["note"], f'{w["n"]}: {e(shared)}.' if shared else "") if x)
        caption = view["l"] + (f'<span class="src">{note}</span>' if note else "")
        tables.append(f'<div class="table-scroll" tabindex="0" role="region" aria-label="{e(w["datatable"])}: {e(view["l"])}">\n<table>\n'
                      f'<caption>{caption}</caption>\n<thead><tr>{"".join(head)}</tr></thead>\n'
                      f'<tbody>\n{chr(10).join(body)}\n</tbody>\n</table>\n</div>')
    # What was measured on, inside the caption: per view where the rows share it, per row where they do not.
    sizes = []
    for view in views:
        size = view["n"] or "; ".join(f'{row["l"]}: {row["n"]}' for row in view["rows"] if row["n"])
        if size:
            sizes.append((view["l"], size))
    if len({size for _, size in sizes}) == 1:  # the same for every view: said once
        sizes = [("", sizes[0][1])]
    measured_on = (' <span class="chart-n"><i>n</i>: ' + e(" · ".join(f"{label}: {size}" if label else size for label, size in sizes)) + ".</span>") if sizes else ""
    source = fill(spec["source"], lang, how)
    # On paper a figure shows its first view; the others are in the appendix of data tables.
    several = f' <span class="print-only">{w["first"].format(view=e(views[0]["l"]))}</span>' if len(views) > 1 else ""
    data["words"]["tap"] = w["tap"]
    if not re.fullmatch(r"[a-z0-9-]+", name):
        sys.exit(f"research: a figure's name is its id in the page, so '{name}' must be lower-case letters, digits and hyphens")
    if all(number != page.figures for number, _ in numbering(page)["tables"]):
        numbering(page)["tables"].append((page.figures, tables))
    made = (f'<figure class="chart" id="fig-{name}" aria-labelledby="fig-{name}-title" data-chart data-brand="{page.product.id}">\n'
            f'<p class="chart-sub">{fill(spec["sub"], lang, how)}</p>\n'
            f'<div class="chart-plot" hidden></div>\n'
            f'<details class="chart-data" open>\n<summary>{w["datatable"]}</summary>\n{chr(10).join(tables)}\n</details>\n'
            f'<figcaption><b>{w["figure"]} {page.figures}.</b> <span class="chart-title" id="fig-{name}-title">{fill(spec["title"], lang, how)}.</span> '
            f'{fill(spec["caption"], lang, how)}{measured_on}{several} <span class="src">{w["source"]}: {source}</span></figcaption>\n'
            f'<script type="application/json">{json.dumps(data, ensure_ascii=False).replace("</", "<\\/")}</script>\n</figure>')
    return whole(made, name)


# Stage diagrams ---------------------------------------------------------------------------------

def pipeline(spec: dict, name: str, page) -> str:
    """Rows of one box or two side by side; each box is (kind, title, lines): kind is model, rule or human."""
    lang, w, e = page.lang, chart_words(page.lang), html.escape
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
    return whole(f'<figure id="fig-{name}">\n'
            f'<svg class="diagram diagram-pipeline" viewBox="0 0 440 {y - 12}" role="img" aria-labelledby="{name}-title {name}-desc" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{name}-title">{e(pick(spec["title"], lang))}</title><desc id="{name}-desc">{e(pick(spec["desc"], lang))}</desc>{"".join(out)}</svg>\n'
            f'<ul class="legend" aria-hidden="true">\n<li><i class="model"></i>{pick(legend[0], lang)}</li>\n<li><i></i>{pick(legend[1], lang)}</li>\n'
            f'<li><i class="human"></i>{pick(legend[2], lang)}</li>\n</ul>\n'
            f'<figcaption><b>{w["figure"]} {page.figures}.</b> {pick(spec["caption"], lang)}</figcaption>\n</figure>', name)
