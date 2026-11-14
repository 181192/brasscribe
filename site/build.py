"""Build the public site into site/_site. Standard library only (Python 3.12+).

The family page (site/family) is the site's home; every other folder in site/ with a product.toml is a
product, served under its own name with the same pages at the same names. site/README.md says what goes where.

One address per page, in both languages. A page is its structure (pages/<name>.html) and its words, kept
apart: <name>.en.toml and <name>.nb.toml beside it, over the product's text.<lang>.toml, over
site/shared/text.<lang>.toml. In the HTML, `data-t="key"` on an empty element takes the words, and
`data-t-<attribute>="key"` an attribute's. The build writes the page in English and an nb.json beside it,
which site/shared/scribe.js swaps in. It fails when a key is missing in a language, or a page's key is unused.

Links are written from a root and made relative here, so the built site works under any path or host:
  @/…  the product's own folder        @family/…  the family home        @<product>/…  another product
Macros: {{shot <slot> sizes="…" alt="<key>" [load="lazy|high"]}}, {{file <name>}} (the download URL of a release
file), {{releases}}, {{downloads}}, {{figure <name> …}} (a figure drawn from the repository's data:
site/shared/figures.py, or the product's own figures.py), {{data <file> <path/to/value> [as="percent|tenth"]}},
{{say <key>}} (the words of a key, where an element cannot take them), and the research pages' measurements,
figures, citations and cross-references ({{data <key> [format]}}, {{chart …}}, {{cite …}}, {{ref …}} and more:
site/research.py, which also checks the papers once every page is written). What a macro draws differently in the
two languages is swapped as a whole; a number or a reference it prints differently is swapped where it stands. A page's header may name `styles:` and `scripts:`.
"""

from __future__ import annotations

import html
import importlib.util
import json
import posixpath
import re
import shutil
import struct
import sys
import tomllib
from pathlib import Path

import research

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
OUT = SITE / "_site"
LANGS = ("en", "nb")
# 2x width per kind of screenshot, as site/shared/make_shots.py writes them.
SHOT_WIDTH = {"phone": 600, "tablet": 720, "desktop": 1440, "mac": 1440}
BLOCKS = {"shot", "figure", "downloads", "chart", "pipeline", "references", "figuretables"}  # macros that draw something; the others give a word or an address


# The product a release file belongs to, from the start of its name: each product has its own releases, and
# PRODUCT-latest holds its newest files (scripts/release.sh has every product's files).
RELEASE_PRODUCTS = (("brasscribe-bandroom-", "bandroom"), ("brasscribe-play-", "brasscribe"), ("fretscribe-", "fretscribe"),
                    ("scribe-core-", "scribe-core"))


def release_product(name: str) -> str:
    for start, product in RELEASE_PRODUCTS:
        if name.startswith(start):
            return product
    raise SystemExit(f"site: {name} is not a file of any product's release (site/build.py, RELEASE_PRODUCTS)")


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"site_{path.parent.name}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def figures():
    if "module" not in figures.__dict__:
        figures.module = load(SITE / "shared" / "figures.py")
    return figures.module


def flat(table: dict, prefix: str = "") -> dict:
    """A TOML table as one level of keys: [hero] lead = … is hero.lead."""
    out = {}
    for key, value in table.items():
        if isinstance(value, dict):
            out.update(flat(value, f"{prefix}{key}."))
        else:
            out[prefix + key] = value
    return out


def words(path_for) -> dict[str, dict]:
    """A table of words in both languages; the two files must hold the same keys."""
    tables = {lang: flat(tomllib.loads(path_for(lang).read_text())) if path_for(lang).exists() else {} for lang in LANGS}
    missing = set(tables["en"]) ^ set(tables["nb"])
    if missing:
        sys.exit(f"{path_for('en').relative_to(SITE)} and its nb twin differ in: {', '.join(sorted(missing))}")
    return tables


def rel(here: str, there: str) -> str:
    """A relative link from the page folder `here` to the folder or file `there`."""
    link = posixpath.relpath(there or ".", here or ".")
    if "." not in posixpath.basename(there) or there.endswith("/"):
        link += "/"
    return "./" if link == "./" else link


def png_height(path: Path, width: int) -> int:
    w, h = struct.unpack(">II", path.read_bytes()[16:24])
    return round(h * width / w)


class Product:
    def __init__(self, folder: Path, site: dict):
        self.id = folder.name
        self.dir = folder
        self.data = tomllib.loads((folder / "product.toml").read_text())
        self.family = self.data.get("family", False)
        self.mount = "" if self.family else self.data.get("mount", self.id).strip("/")
        self.url = self.data.get("url")  # set when the product is served from a host of its own
        self.releases = self.data.get("releases", site["releases"]).rstrip("/")
        self.brand = ROOT / self.data["brand"]
        self.paths = self.data.get("paths", {})  # a page's file name -> the name it is served under
        self.text = words(lambda lang: folder / f"text.{lang}.toml")
        self.kinds = {}
        shots = folder / "shots.txt"
        if shots.exists():
            for line in shots.read_text().splitlines():
                cols = line.split()
                if len(cols) >= 3 and not line.startswith("#"):
                    self.kinds[cols[0]] = cols[1]

    def figures(self):
        """The product's own figures (site/<product>/figures.py), when it has any."""
        if not hasattr(self, "_figures"):
            self._figures = load(self.dir / "figures.py") if (self.dir / "figures.py").exists() else None
        return self._figures

    def pages(self) -> dict[str, Path | None]:
        """Its pages by file name. A page still kept as one whole file per language (pages/en, pages/nb) counts too."""
        found = {p.stem: p for p in sorted((self.dir / "pages").glob("*.html"))}
        if not self.family:
            found.setdefault("index", SITE / "shared" / "product.html")  # every app's front page has one structure
        for old in sorted((self.dir / "pages" / "en").glob("*.html")):
            found.setdefault(old.stem, old)
        if self.data.get("downloads") and "download" not in found:
            found["download"] = None  # made from the product's data
        return found

    def served(self, name: str) -> str:
        return "" if name == "index" else self.paths.get(name, name)

    def downloads(self, shared: list[dict]) -> list[dict]:
        return self.data.get("downloads", []) + (shared if self.data.get("downloads") else [])


class Page:
    def __init__(self, site: "Site", product: Product, name: str, source: Path | None):
        self.site, self.product, self.name, self.source = site, product, name, source
        self.dir = posixpath.join(product.mount, product.served(name))
        self.lang = "en"
        self.meta, self.body, self.used, self.slots, self.plain, self.inline = {}, {}, set(), {}, False, {}
        self.whole = bool(source and source.parent.name in LANGS)  # one whole file per language
        own = words(lambda lang: product.dir / "pages" / f"{name}.{lang}.toml") if source and not self.whole else {lang: {} for lang in LANGS}
        self.own = set(own["en"])
        self.table = {lang: {**site.text[lang], **product.text[lang], **own[lang]} for lang in LANGS}
        if source:
            for lang in LANGS if self.whole else ("en",):
                text = (source.parent.parent / lang / source.name if self.whole else source).read_text()
                head = re.match(r"<!--\n(.*?)\n-->\n", text, re.S)
                if not head:
                    sys.exit(f"{source}: a page starts with a <!-- … --> header")
                for line in head.group(1).splitlines():
                    key, _, value = line.partition(":")
                    self.meta[key.strip() if lang == "en" else f"{key.strip()}.nb"] = value.strip()
                self.body[lang] = text[head.end():]

    # Words -----------------------------------------------------------------------------------
    def say(self, key: str, **values) -> str:
        """The words of a key in the language being written, with {names} filled in."""
        if key not in self.table[self.lang]:
            sys.exit(f"{self.dir or '/'}: no words for '{key}'")
        self.used.add(key)
        said = self.table[self.lang][key]
        return said.format(**values) if values and isinstance(said, str) else said

    def group(self, prefix: str) -> dict:
        """Every key under a prefix, as a table of its own: the words a figure hands to its script."""
        found = {key[len(prefix):]: value for key, value in self.table[self.lang].items() if key.startswith(prefix)}
        self.used |= {prefix + key for key in found}
        return found

    def number(self, value: float, digits: int = 1) -> str:
        """A number as the language writes it: a decimal comma in Norwegian."""
        said = f"{value:.{digits}f}"
        return said.replace(".", ",") if self.lang == "nb" else said

    def named(self, key: str) -> list[str]:
        """The files a page's header names under `styles:` or `scripts:`, separated by spaces or commas."""
        return self.meta.get(key, "").replace(",", " ").split()

    # Links -----------------------------------------------------------------------------------
    def link(self, root: str, path: str = "") -> str:
        """Resolve @<root>/<path> from this page."""
        product = self.product
        if root not in ("", "lang"):
            product = self.site.family if root == "family" else self.site.products.get(root)
            if product is None:
                sys.exit(f"{self.dir}: @{root}/ names no product")
            if product.url and product is not self.product:
                return product.url.rstrip("/") + "/" + path
        page, _, frag = path.partition("#")
        first = page.split("/")[0]
        if first in product.paths:  # a page named by its file ("research/") is linked where it is served
            page = product.paths[first] + page[len(first):]
        target = posixpath.normpath(posixpath.join(product.mount, page))
        if page.endswith("/") or not page:
            target += "/"
        link = rel(self.dir, target)
        if frag:
            return "#" + frag if link == "./" else link + "#" + frag
        return link

    def links(self, text: str) -> str:
        return re.sub(r"""(?<=["' ,(])@(\w*)/([^"'\s<>)]*)""", lambda m: self.link(m.group(1), m.group(2)), text)

    # Macros ----------------------------------------------------------------------------------
    def shot(self, slot: str, sizes: str, alt: str, load: str = "", product: Product | None = None, folder: str = "", said: str | None = None) -> str:
        """A screenshot. `alt` is the key of its description, unless the description itself is handed in as `said`."""
        product = product or self.product
        folder = folder or f"@{product.id}/assets/shots"
        kind = product.kinds.get(slot)
        if kind is None:
            sys.exit(f"{self.dir}: no screenshot '{slot}' in {product.id}/shots.txt")
        shots = product.dir / "shots"
        # A screen that was not captured in this language shows the English one.
        lang = self.lang if (shots / f"{slot}-{self.lang}-light.png").exists() else "en"
        full = SHOT_WIDTH[kind]
        base = f"{folder}/{slot}-{lang}"
        lines = ["<picture>"]
        for theme, media in (("dark", ' media="(prefers-color-scheme: dark)"'), ("light", "")):
            if not (shots / f"{slot}-{lang}-{theme}.avif").exists():
                continue
            for ext in ("avif", "webp"):
                lines.append(f'  <source type="image/{ext}"{media} srcset="{base}-{theme}-1x.{ext} {full // 2}w, '
                             f'{base}-{theme}.{ext} {full}w" sizes="{sizes}">')
        height = png_height(shots / f"{slot}-{lang}-light.png", full)
        attr = {"lazy": ' loading="lazy"', "high": ' fetchpriority="high"', "": ""}[load]
        lines.append(f'  <img src="{base}-light.png" width="{full}" height="{height}"{attr} alt="{html.escape(said if said is not None else self.say(alt), quote=True)}">')
        lines.append("</picture>")
        return "\n".join(lines)

    def file(self, name: str) -> str:
        # Every product's release has checksums of its own: a page links to its product's.
        product = self.product.id if name == "SHA256SUMS" and not self.product.family else release_product(name)
        return f"{self.product.releases}/download/{product}-latest/{name}"

    def releases(self) -> str:
        """The page of the product's newest release; the list of every release for a page of no one product."""
        base = self.product.releases
        return base if self.product.family else f"{base}/tag/{self.product.id}-latest"

    def downloads_table(self) -> str:
        rows = "".join(
            f'\n    <tr><th scope="row"><a href="{self.file(d["file"])}"><code>{d["file"]}</code></a></th><td>{d[self.lang]}</td></tr>'
            for d in self.product.downloads(self.site.shared_downloads))
        return (f'<div class="table-scroll" role="region" aria-labelledby="download-caption" tabindex="0">\n<table>\n'
                f'  <caption id="download-caption">{self.say("downloads.files")}</caption>\n'
                f'  <thead><tr><th scope="col">{self.say("downloads.file")}</th><th scope="col">{self.say("downloads.for")}</th></tr></thead>\n'
                f"  <tbody>{rows}\n  </tbody>\n</table>\n</div>")

    def figure(self, name: str, args: dict) -> str:
        """A figure by name: the product's own, else a shared one. product="<id>" draws another product's (family home)."""
        owner = self.site.products[args.pop("product")] if "product" in args else self.product
        draw = getattr(owner.figures(), name, None) or getattr(figures(), name, None)
        if draw is None:
            sys.exit(f"{self.dir}: no figure named {name}")
        self.shared = figures()  # a product's figures use the shared ones' helpers
        mine, table = self.product, self.table
        # The figure reads its words from the product it is about.
        if owner is not mine:  # and its front page's
            front = words(lambda lang: owner.dir / "pages" / f"index.{lang}.toml")
            self.product, self.table = owner, {lang: {**table[lang], **owner.text[lang], **front[lang]} for lang in LANGS}
        try:
            return self.links(" " + draw(self, **args))[1:]  # its addresses are the product's own
        finally:
            self.product, self.table = mine, table

    def macro(self, name: str, rest: str) -> str:
        args = dict(re.findall(r'([\w-]+)="([^"]*)"', rest))
        bare = re.sub(r'[\w-]+="[^"]*"', "", rest).split()
        if name == "file":
            return self.file(bare[0])
        if name == "releases":
            return self.releases()
        if name == "say":
            return self.say(bare[0])
        if name == "data" and (len(bare) == 1 or bare[1] in research.FORMATS):  # a named measurement: site/research.py
            return research.macro(self, name, bare, args)
        if name in research.MACROS:
            return research.macro(self, name, bare, args)
        if name == "data":
            value = figures().lookup(bare[0], bare[1])
            return str(round(value * 100)) if args.get("as") == "percent" else str(round(value * 10)) if args.get("as") == "tenth" else str(value)
        if name == "shot":
            other = self.site.products[args["product"]] if "product" in args else None  # the family home shows each app's screens
            return self.shot(bare[0], args["sizes"], args["alt"], args.get("load", ""), other)
        if name == "figure":
            return self.figure(bare[0], args)
        if name == "downloads":
            return self.downloads_table()
        sys.exit(f"{self.dir}: unknown macro {{{{{name}}}}}")

    def macros(self, text: str) -> str:
        """Run the macros of a text. What a drawing macro gives differently in Norwegian becomes a slot the script swaps;
        a word or a number that reads differently (0.66, 0,66) becomes a span with its Norwegian by key."""
        if self.plain:  # words or a whole body in one language: its macros are written in that language as they stand
            return re.sub(r"\{\{(\w+)([^{}]*)\}\}", lambda m: self.macro(m.group(1), m.group(2)), text)

        def run(m: re.Match) -> str:
            name, rest = m.group(1), m.group(2)
            made = {}
            for lang in LANGS:
                self.lang = lang
                made[lang] = self.macro(name, rest)
            self.lang = "en"
            if name not in BLOCKS:
                if made["nb"] == made["en"]:
                    return made["en"]
                if text.rfind("<", 0, m.start()) > text.rfind(">", 0, m.start()):
                    sys.exit(f"{self.dir}: {{{{{name}{rest}}}}} stands in an attribute and reads differently in Norwegian; "
                             "give the attribute its words by key (data-t-<attribute>)")
                key = f"macro.{len(self.inline) + 1}"
                self.inline[key] = made["nb"]
                return f'<span data-t="{key}">{made["en"]}</span>'
            # A block keeps the indentation of the line its macro stands on.
            before = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            shown = made["en"].replace("\n", "\n" + before) if before.isspace() else made["en"]
            if made["nb"] == made["en"]:
                return shown
            slot = f"s{len(self.slots) + 1}"
            self.slots[slot] = made["nb"]
            return f'<div class="slot" data-slot="{slot}">{shown}</div>'
        return re.sub(r"\{\{(\w+)([^{}]*)\}\}", run, text)

    # The download page, from the product's data ----------------------------------------------
    def download_page(self, lang: str) -> str:
        """The download page, in a player's words: the variant rail at the top, then a panel for each place the app
        runs, under the rail's anchors. A panel has one main button per device, three steps for the first time, and
        the release files themselves folded away for the band's tech person; no file name is a button. Then, as
        the fixed second step, Bandroom on the computer; the tech person's tools last."""
        self.lang = lang
        p, shared = self.product, figures()
        self.shared = shared
        groups: dict[str, list[dict]] = {}
        for item in p.downloads(self.site.shared_downloads):
            groups.setdefault(item["group"], []).append(item)
        say = self.say

        def tech(names: list[str]) -> str:
            rows = "".join(f'\n      <li><a href="{self.file(x["file"])}"><code>{x["file"]}</code></a> <span class="muted">{x[lang]}</span></li>'
                           for g in names for x in groups[g])
            return (f'  <details class="tech"><summary>{say("download.tech")}</summary>\n    <ul class="tech-files">{rows}\n    </ul>'
                    f'\n    <p><a href="{self.file("SHA256SUMS")}">{say("download.sums")}</a></p>\n  </details>')

        def device(group: str, primary: bool) -> str:
            steps = "".join(f"<li>{step}</li>" for step in say(f"groups.{group}.steps"))
            return (f'  <div class="dl-device" data-group="{group}">\n    <a class="button {"primary" if primary else "outline"}" href="{self.file(groups[group][0]["file"])}">{say(f"groups.{group}.button")}</a>\n'
                    f'    <p class="first-title">{say("download.first", device=say(f"groups.{group}.title"))}</p>\n    <ol class="first-steps">{steps}</ol>\n  </div>')

        parts = [f'<h1>{say("download.heading")}</h1>\n<p class="lead">{say("download.lead")}</p>\n{shared.rail(self)}\n<div class="download-groups">']
        for v in shared.places(self):
            vid, w = v["id"], v[lang]
            head = (f'<section id="{vid}" class="download-panel{" shared" if vid == "bandroom" else ""}" aria-labelledby="{vid}-title">\n'
                    f'  <h2 id="{vid}-title">{say("download.then") if vid == "bandroom" else say(f"variants.{vid}.title", app=p.data["name"])}</h2>\n'
                    f'  <p class="variant-does">{w["does"]}</p>\n  {shared.tags(self, v)}\n  <p class="variant-needs">{w["needs"]}</p>')
            if vid == "bandroom":  # the second step, the same for every app: its buttons stay outlined
                body = ('  <div class="actions">' + "".join(f'<a class="button outline" href="{self.file(x["file"])}">{x.get("label_" + lang)}</a>' for x in groups["bandroom"])
                        + f'</div>\n  <p class="more-link"><a href="@family/bandroom/">{say("download.bandroom")}</a></p>\n' + tech(["bandroom"]))
            elif vid == "studio":
                body = f'  <p class="more-link"><a href="#bandroom">{say("variants.studio.download")}</a></p>'
            elif vid == "tablet":  # the phone's files: said once, under the phone
                body = f'  <p>{say("download.tablet")}</p>'
            else:
                body = "\n".join(device(g, i == 0) for i, g in enumerate(v["files"])) + "\n" + tech(v["files"])
            parts.append(f"{head}\n{body}\n</section>")
        # The tools are for the tech person too: what they are is said, the files (and their processors) are folded.
        parts.append(f'<section id="tools" aria-labelledby="tools-title">\n  <h2 id="tools-title">{say("groups.tools.title")}</h2>\n'
                     f'  <p>{say("groups.tools.note")}</p>\n  <details class="tech"><summary>{say("download.files")}</summary>\n    <ul class="tech-files">'
                     + "".join(f'\n      <li><a href="{self.file(x["file"])}"><code>{x["file"]}</code></a> <span class="muted">{x[lang]}</span></li>' for x in groups["tools"])
                     + '\n    </ul>\n  </details>\n</section>')
        parts.append(f'</div>\n<p class="muted">{say("download.more")}</p>\n')
        self.lang = "en"
        return "\n".join(parts)

    # Words into the structure ----------------------------------------------------------------
    def fill(self, text: str, nb: dict) -> str:
        """English into every data-t element and data-t-<attribute>; the Norwegian of each into `nb`."""
        def both(key: str) -> dict:
            said = {}
            was, self.plain = self.plain, True  # words are in one language, and so is what their macros give
            for lang in LANGS:
                self.lang = lang
                said[lang] = self.links(" " + self.macros(str(self.say(key))))[1:]
            self.lang, self.plain = "en", was
            return said

        def element(m: re.Match) -> str:
            said = both(m.group(3))
            nb["t"][m.group(3)] = said["nb"]
            return f'<{m.group(1)}{m.group(2)} data-t="{m.group(3)}"{m.group(4)}>{said["en"]}</{m.group(1)}>'

        def attribute(m: re.Match) -> str:
            said = both(m.group(2))
            nb["a"][m.group(2)] = said["nb"]
            return f'{m.group(0)} {m.group(1)}="{html.escape(said["en"], quote=True)}"'

        text = re.sub(r'<(\w+)([^<>]*?) data-t="([^"]+)"([^<>]*)></\1>', element, text)
        return re.sub(r' data-t-([\w-]+)="([^"]+)"', attribute, text)

    # The whole page --------------------------------------------------------------------------
    def chrome(self) -> tuple[str, str]:
        """What stands around every page: the line bar and the app's own row above, the footer below.

        The bar is a path from the line down: Scribe, then its apps, the one you are in marked. Scribe is the root of
        the path and never the marked step; on the family's own pages its pen is down (the line runs to the edge).
        Under it, each app has the same row: its name and the same four pages in the same order."""
        p, site = self.product, self.site
        apps = []
        for q in site.products.values():
            here = "" if q is not p else ' aria-current="page"' if self.link(q.id, "") == "./" else ' aria-current="true"'
            apps.append(f'\n        <li><a href="@{q.id}/"{here}><span class="chip" style="--chip: var(--family-chip-{q.id})"></span>{q.data["name"]}</a></li>')
        home = ' aria-current="page"' if p.family and self.link("family", "") == "./" else ""
        bandroom = ' aria-current="page"' if p.family and self.name == "bandroom" else ""
        bar = f"""<header class="family-bar{" pen-down" if p.family else ""}">
  <div class="wrap">
    <nav class="line-path" data-t-aria-label="bar.apps">
      <a class="family-mark" href="@family/"{home} data-t-aria-label="bar.home">{site.mark}<span data-t="bar.all"></span></a>
      <span class="line-sep" aria-hidden="true">/</span>
      <ul class="line-apps">{"".join(apps)}
      </ul>
      <span class="line-rule" aria-hidden="true"></span>
      <a class="line-bandroom" href="@family/bandroom/"{bandroom}>Bandroom</a>
    </nav>
    <button type="button" class="lang-switch" data-lang-switch hidden></button>
    <noscript><span class="lang-note" data-t="bar.noscript"></span></noscript>
  </div>
</header>
"""
        row = ""
        if not p.family:
            # The same pages in the same order for every product.
            items = [("nav.overview", "@/"), ("nav.guide", "@/guide/"), ("nav.download", "@/download/"), ("nav.how", "@/how-it-works/")]
            items = [(key, href) for key, href in items if href == "@/" or href.strip("@/") in {p.served(n) for n in p.pages()}]
            nav = []
            for key, href in items:
                current = ' aria-current="page"' if self.link("", href[2:]) == "./" else ""
                nav.append(f'\n        <li><a href="{href}"{current} data-t="{key}"></a></li>')
            row = f"""<nav class="product-nav" data-t-aria-label="nav.label">
  <div class="wrap">
    <span class="app-name">{p.data["name"]}</span>
    <ul>{"".join(nav)}
    </ul>
  </div>
</nav>
"""
        # One footer everywhere: the line and everything in it, then the credits of the page's owner.
        here = lambda q: ' class="here"' if q is p else ""
        links = "".join(f'<a href="@{q.id}/"{here(q)}>{q.data["name"]}</a>' for q in site.products.values())
        foot = f"""<footer class="site-footer">
  <div class="wrap">
    <p class="footer-line"><a class="family-mark" href="@family/">{site.mark}<span data-t="bar.all"></span></a>{links}<a href="@family/bandroom/"{' class="here"' if self.name == "bandroom" else ""}>Bandroom</a><a href="{site.source}" data-t="footer.source"></a></p>
    <p class="footer-note" data-t="{"footer.note" if self.whole else self.meta.get("footer", "footer.note")}"></p>
  </div>
</footer>"""
        return bar + row, foot

    def render(self) -> tuple[str, dict]:
        p, site = self.product, self.site
        nb = {"t": {}, "a": {}, "slots": self.slots}
        if self.name == "download" and not self.source:
            self.meta = {"main_class": "wrap downloads"}
            self.body = {lang: self.download_page(lang) for lang in LANGS}
            self.whole = True
            titles = {lang: (self.table[lang]["download.title"], self.table[lang]["download.description"]) for lang in LANGS}
            self.used |= {"download.title", "download.description"}
        elif self.whole:
            titles = {"en": (self.meta["title"], self.meta["description"]), "nb": (self.meta["title.nb"], self.meta["description.nb"])}
        else:
            titles = {lang: (self.table[lang]["title"], self.table[lang]["description"]) for lang in LANGS}
            self.used |= {"title", "description"}
        if self.whole:
            # One whole body per language: the Norwegian one is swapped in as it is.
            bodies, sources = {}, self.body
            for lang in LANGS:
                # While a language is written, the page is that language's page: its body, its numbering.
                self.lang, self.plain, self.body = lang, True, sources[lang]
                bodies[lang] = self.links(self.macros(self.body).replace("@lang/", "@/"))
            self.lang, self.plain, self.body = "en", False, sources
            nb["main"] = bodies["nb"].rstrip()
            main = bodies["en"]
        else:
            main = self.body["en"]
        top, foot = self.chrome()
        head = [f'<title>{titles["en"][0]}</title>',
                f'<meta name="description" content="{html.escape(titles["en"][1], quote=True)}">',
                '<meta name="color-scheme" content="light dark">',
                f'<meta property="og:title" content="{html.escape(titles["en"][0], quote=True)}">',
                f'<meta property="og:description" content="{html.escape(titles["en"][1], quote=True)}">']
        image = self.meta.get("og_image") or p.data.get("og_image")
        if image:
            # Addresses for other sites are whole: the site's address, the product's folder, the file.
            whole = site.base + posixpath.join(p.mount, image.removeprefix("@/")) if site.base else image
            head.append(f'<meta property="og:image" content="{whole}">')
        if site.base:
            head.append(f'<link rel="canonical" href="{site.base}{self.dir.strip("/") + "/" if self.dir.strip("/") else ""}">')
        # The language is chosen before anything is drawn, so a Norwegian reader does not see English flash by.
        head.append(f"<script>{site.early}</script>")
        # What only a script can work has its room on the page from the start; without scripts it takes none.
        head.append("<noscript><style>.await-js { display: none !important; }</style></noscript>")
        for font in p.data.get("preload", []):  # the headline's face, so the headline is not drawn twice
            head.append(f'<link rel="preload" href="@/assets/fonts/{font}" as="font" type="font/ttf" crossorigin>')
        head.append('<script type="module" src="@family/scribe.js"></script>')
        head.append('<script type="module" src="@family/rail.js"></script>')
        head.append('<link rel="icon" href="@/favicon.svg" type="image/svg+xml">')
        if "icons" in p.data:
            head += ['<link rel="icon" href="@/favicon.ico" sizes="any">', '<link rel="apple-touch-icon" href="@/apple-touch-icon.png">']
        for css in [f'assets/{p.data["css"]}', "assets/fonts.css", "site.css", *self.named("styles"), *p.data.get("styles", [])]:
            head.append(f'<link rel="stylesheet" href="@/{css}">')
        for script in self.named("scripts"):
            head.append(f'<script type="module" src="@/{script}"></script>')
        main_class = f' class="{self.meta["main_class"]}"' if "main_class" in self.meta else ""
        page = f"""<!doctype html>
<html lang="en" data-product="{p.id}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {"\n  ".join(head)}
</head>
<body>
<a class="skip" href="#main" data-t="bar.skip"></a>

{top}
<main id="main"{main_class}>
{main.rstrip()}
</main>

{foot}
</body>
</html>
"""
        page = re.sub(r"[ \t]*<!--slot\b.*?-->\n?", "", page, flags=re.S)  # content slots are for authors
        if not self.whole:
            page = self.macros(page)
        page = self.links(self.fill(page, nb))
        nb["slots"] = {k: self.links(" " + v)[1:] for k, v in self.slots.items()}
        nb["t"] |= {k: self.links(" " + v)[1:] for k, v in self.inline.items()}
        if "main" in nb:
            nb["main"] = self.links(nb["main"])
        nb["title"], nb["description"] = titles["nb"]
        unused = self.own - self.used
        if unused:
            sys.exit(f"{self.dir or '/'}: words nothing uses: {', '.join(sorted(unused))}")
        return page, nb


class Site:
    def __init__(self):
        conf = tomllib.loads((SITE / "shared" / "site.toml").read_text())
        self.base = conf.get("base", "").rstrip("/") + "/" if conf.get("base") else ""
        self.redirects = conf.get("redirects", {})
        self.source = conf["source"]
        self.bandroom = conf["bandroom"]  # Bandroom's place on every app's rail
        self.shared_downloads = conf.get("downloads", [])
        self.text = words(lambda lang: SITE / "shared" / f"text.{lang}.toml")
        scribe = ROOT / "design" / "brands" / "scribe"
        self.mark = (scribe / "brand" / "mark.svg").read_text().strip()
        self.line = (scribe / "dist" / "web" / "line.css").read_text()  # what the family puts on every page: the bar, the pen, the doubt mark
        self.glyphs = {f.stem: f.read_text().strip() for f in sorted((scribe / "dist" / "web" / "variants").glob("*.svg"))}
        self.early = re.sub(r"\s*\n\s*", "", (SITE / "shared" / "early.js").read_text().split("*/", 1)[-1])
        every = [Product(f.parent, conf) for f in sorted(SITE.glob("*/product.toml"))]
        self.products = {p.id: p for p in every if not p.family}
        self.family = next(p for p in every if p.family)
        self.all = every

    def copy_brand(self, p: Product, assets: Path, logo_dir: Path) -> None:
        web = p.brand / "dist" / "web"
        assets.mkdir(parents=True, exist_ok=True)
        if (web / "fonts").exists():  # the family has no face of its own
            shutil.copytree(web / "fonts", assets / "fonts", dirs_exist_ok=True)
        logo_dir.mkdir(parents=True, exist_ok=True)
        for logo in p.data.get("marks", []):
            shutil.copy(p.brand / logo, logo_dir)

    def build(self) -> None:
        if OUT.exists():
            shutil.rmtree(OUT)
        for p in self.all:
            out = OUT / p.mount
            web = p.brand / "dist" / "web"
            self.copy_brand(p, out / "assets", out / "assets" / "logo")
            shutil.copy(web / p.data["css"], out / "assets")
            shutil.copy(web / "fonts.css", out / "assets")
            # Each product's folder holds everything its pages load but the language script, which is the family's.
            (out / "site.css").write_text(self.line + "\n" + (SITE / "shared" / "site.css").read_text())
            for css in p.data.get("styles", []):
                if (p.dir / css).exists():  # the family's brands.css is made below
                    shutil.copy(p.dir / css, out)
            if "icons" in p.data:
                for icon in (p.brand / p.data["icons"]).iterdir():
                    shutil.copy(icon, out)
            else:
                shutil.copy(p.brand / p.data["favicon"], out / "favicon.svg")
            for kept, served in (("shots", "shots"), ("figures", "data")):
                if (p.dir / kept).exists():
                    shutil.copytree(p.dir / kept, out / "assets" / served)
            if p.family:
                self.family_assets(out / "assets")
                shutil.copy(SITE / "shared" / "scribe.js", out)
                shutil.copy(SITE / "shared" / "rail.js", out)
            for name, source in p.pages().items():
                page = Page(self, p, name, source)
                # What a page names in its header: from the product's folder, else from site/shared.
                for extra in page.named("styles") + page.named("scripts"):
                    found = [d / extra for d in (p.dir, SITE / "shared") if (d / extra).exists()]
                    if not found:
                        sys.exit(f"{page.dir}: {extra} is neither in {p.dir.name}/ nor in shared/")
                    shutil.copy(found[0], out)
                text, nb = page.render()
                target = OUT / page.dir / "index.html"  # a folder per page, so URLs have no .html
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
                (target.parent / "nb.json").write_text(json.dumps(nb, ensure_ascii=False, separators=(",", ":")))
        self.stubs()
        (OUT / ".nojekyll").touch()

    def stubs(self) -> None:
        """An address the site used to have sends its visitor on to where the page is now."""
        for old, new in self.redirects.items():
            folder = OUT / old.strip("/")
            if (folder / "index.html").exists():
                sys.exit(f"redirect {old}: a page is served there")
            path, _, query = new.partition("?")
            to = rel(old.strip("/"), (path.strip("/") or ".") + "/") + ("?" + query if query else "")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "index.html").write_text(
                f'<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n  <title>This page has moved</title>\n'
                # The script keeps the place on the page the old address pointed at (#…).
                # The script keeps ?lang= when the old address had it and the new one does not say a language itself.
                f'  <script>location.replace("{to}" + {"\"\"" if "?" in to else "location.search"} + location.hash)</script>\n'
                f'  <noscript><meta http-equiv="refresh" content="0; url={to}"></noscript>\n  <link rel="canonical" href="{to}">\n  <meta name="robots" content="noindex">\n'
                f'</head>\n<body>\n<p>This page has moved: <a href="{to}">go to the new address</a>.</p>\n</body>\n</html>\n')

    def family_assets(self, assets: Path) -> None:
        """The family home shows each product in its own brand: tokens scoped to [data-brand], fonts, logo, shots, figures."""
        css = []
        for p in self.products.values():
            web = p.brand / "dist" / "web"
            self.copy_brand(p, assets / p.id, assets / p.id / "logo")
            css.append((web / "fonts.css").read_text().replace('url("fonts/', f'url("{p.id}/fonts/'))
            css.append((web / p.data["css"]).read_text().replace(":root", f'[data-brand="{p.id}"]'))
        (assets / "brands.css").write_text("\n".join(css))


def check(out: Path) -> None:
    """Every local link and image in the built pages points at something that was built, and a link to a place on a
    page (#…) at a place that page has, in English and in Norwegian (nb.json may add ids of its own)."""
    bad, ids = [], {}
    for page in out.rglob("index.html"):
        found = set(re.findall(r'\bid="([^"]+)"', page.read_text()))
        nb = page.parent / "nb.json"
        if nb.exists():
            found |= set(re.findall(r'\bid=\\?"([^"\\]+)', nb.read_text()))
        ids[page.resolve()] = found
    for page in out.rglob("index.html"):
        text = page.read_text()
        for attr, value in re.findall(r'(?<![-\w])(href|src|srcset)="([^"]*)"', text):
            for url in ([u.split()[0] for u in value.split(", ")] if attr == "srcset" else [value]):
                if re.match(r"[a-z]+:", url):
                    continue
                path, _, frag = html.unescape(url).partition("#")
                target = (page.parent / path.split("?")[0]).resolve()
                if target.is_dir():
                    target = target / "index.html"
                if not target.exists() or out.resolve() not in target.parents:
                    bad.append(f"{page.relative_to(out)}: {url}")
                elif frag and target in ids and frag not in ids[target]:
                    bad.append(f"{page.relative_to(out)}: no id for {url}")
    if bad:
        sys.exit("broken links:\n  " + "\n  ".join(bad))


if __name__ == "__main__":
    Site().build()
    check(OUT)
    research.finish(OUT)
    print(f"site built in {OUT}")
