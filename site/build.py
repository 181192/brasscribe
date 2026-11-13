"""Build the public site into site/_site. Standard library only (Python 3.11+).

Every folder in site/ with a product.toml is a product: its pages (pages/<lang>/<name>.html, the
inside of <main> under a small header), its screenshots (shots/, made by site/shared/make_shots.py)
and its data. The layout around the pages, the download page and the family page's product sheets
come from here, so a new product is a new folder. site/README.md says what goes in it.

In pages and in product.toml, links are written from a root and made relative here, so the built
site works under any path or host:
  @/…          the product's own folder (assets, icons)
  @lang/…      the product's pages in the page's language
  @family/…    the family page, @<product>/… another product, in the page's language
Macros: {{shot <slot> sizes="…" alt="…" [load="lazy|high"]}}, {{file <name>}} (the download URL of a
release file), {{releases}}, {{downloads}} (the table of release files), {{products}} (family page),
{{figure <name> …}} (a figure drawn from the repository's data: site/shared/figures.py, or the product's
own figures.py), {{data <file> <path/to/value> [as="percent"]}} (a number from a JSON file in the repository), and
the research pages' measurements and figures ({{data <key> [format]}}, {{chart …}} and more: site/research.py).
A page's header may name `styles:` and `scripts:` (files in the product's folder or in site/shared).
"""

from __future__ import annotations

import html
import importlib.util
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
WORDS = {
    "en": {"skip": "Skip to content", "nav": "Main", "family": "Scribe apps", "all": "All apps",
           "switch": "Norsk", "download": "Download", "file": "File", "for": "For",
           "files": "Files in the latest release", "home_alt": "{name}, home",
           "see": "See {name}", "made_for": "For", "runs_on": "Runs on"},
    "nb": {"skip": "Hopp til innholdet", "nav": "Hovedmeny", "family": "Scribe-appene", "all": "Alle appene",
           "switch": "English", "download": "Last ned", "file": "Fil", "for": "For",
           "files": "Filene i siste utgivelse", "home_alt": "{name}, forsiden",
           "see": "Se {name}", "made_for": "For", "runs_on": "Kjører på"},
}
# 2x width per kind of screenshot, as site/shared/make_shots.py writes them.
SHOT_WIDTH = {"phone": 600, "tablet": 720, "desktop": 1440, "mac": 1440}


class Product:
    def __init__(self, folder: Path, site: dict):
        self.id = folder.name
        self.dir = folder
        self.data = tomllib.loads((folder / "product.toml").read_text())
        self.mount = self.data.get("mount", self.id).strip("/")
        self.url = self.data.get("url")  # set when the product is served from a host of its own
        self.family = self.data.get("family", False)
        self.releases = self.data.get("releases", site["releases"]).rstrip("/")
        self.brand = ROOT / self.data["brand"]
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

    def home(self, lang: str) -> str:
        """The folder of the product's pages in a language, from the site root."""
        return posixpath.join(self.mount, "" if lang == "en" else lang)

    def pages(self, lang: str) -> dict[str, Path | None]:
        found = {p.stem: p for p in sorted((self.dir / "pages" / lang).glob("*.html"))}
        if self.data.get("downloads") and "download" not in found:
            found["download"] = None  # made from the product's data
        return found

    def downloads(self, shared: list[dict]) -> list[dict]:
        return self.data.get("downloads", []) + (shared if self.data.get("downloads") else [])


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"site_{path.parent.name}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def figures():
    if "module" not in figures.__dict__:
        figures.module = load(SITE / "shared" / "figures.py")
    return figures.module


def rel(here: str, there: str) -> str:
    """A relative link from the page folder `here` to the folder or file `there`."""
    link = posixpath.relpath(there or ".", here or ".")
    if "." not in posixpath.basename(there) or there.endswith("/"):
        link += "/"
    return "./" if link == "./" else link


def png_height(path: Path, width: int) -> int:
    w, h = struct.unpack(">II", path.read_bytes()[16:24])
    return round(h * width / w)


class Page:
    def __init__(self, site: "Site", product: Product, lang: str, name: str, source: Path | None):
        self.site, self.product, self.lang, self.name = site, product, lang, name
        self.dir = posixpath.join(product.home(lang), "" if name == "index" else name)
        self.meta, self.body = {}, ""
        if source:
            text = source.read_text()
            head = re.match(r"<!--\n(.*?)\n-->\n", text, re.S)
            if not head:
                sys.exit(f"{source}: a page starts with a <!-- title: … --> header")
            for line in head.group(1).splitlines():
                key, _, value = line.partition(":")
                self.meta[key.strip()] = value.strip()
            self.body = text[head.end():]

    def named(self, key: str) -> list[str]:
        """The files a page's header names under `styles:` or `scripts:`, separated by spaces or commas."""
        return self.meta.get(key, "").replace(",", " ").split()

    # Links ---------------------------------------------------------------------------------
    def link(self, root: str, path: str = "") -> str:
        """Resolve @<root>/<path> from this page."""
        product = self.product
        if root == "":
            base = product.mount
        elif root == "lang":
            base = product.home(self.lang)
        else:
            product = self.site.family if root == "family" else self.site.products.get(root)
            if product is None:
                sys.exit(f"{self.dir}: @{root}/ names no product")
            if product.url and product is not self.product:
                return product.url.rstrip("/") + "/" + posixpath.join("" if self.lang == "en" else self.lang, path)
            base = product.home(self.lang)
        page, _, frag = path.partition("#")
        target = posixpath.normpath(posixpath.join(base, page))
        if page.endswith("/") or not page:
            target += "/"
        link = rel(self.dir, target)
        if frag:
            return "#" + frag if link == "./" else link + "#" + frag
        return link

    def links(self, text: str) -> str:
        return re.sub(r"""(?<=["' ,(])@(\w*)/([^"'\s<>)]*)""", lambda m: self.link(m.group(1), m.group(2)), text)

    # Macros --------------------------------------------------------------------------------
    def shot(self, slot: str, sizes: str, alt: str, load: str = "", product: Product | None = None,
             folder: str = "@/assets/shots") -> str:
        product = product or self.product
        kind = product.kinds.get(slot)
        if kind is None:
            sys.exit(f"{self.dir}: no screenshot '{slot}' in {product.id}/shots.txt")
        shots = product.dir / "shots"
        # A screen that was not captured in this language shows the English one.
        lang = self.lang if (shots / f"{slot}-{self.lang}-light.png").exists() else "en"
        full = SHOT_WIDTH[kind]
        base = f"{folder}/{slot}-{lang}"
        lines = ["<picture>"]
        themes = (("dark", ' media="(prefers-color-scheme: dark)"'), ("light", ""))
        for theme, media in themes:
            if not (shots / f"{slot}-{lang}-{theme}.avif").exists():
                continue
            for ext in ("avif", "webp"):
                lines.append(f'  <source type="image/{ext}"{media} srcset="{base}-{theme}-1x.{ext} {full // 2}w, '
                             f'{base}-{theme}.{ext} {full}w" sizes="{sizes}">')
        height = png_height(shots / f"{slot}-{lang}-light.png", full)
        attr = {"lazy": ' loading="lazy"', "high": ' fetchpriority="high"', "": ""}[load]
        lines.append(f'  <img src="{base}-light.png" width="{full}" height="{height}"{attr} alt="{alt}">')
        lines.append("</picture>")
        return "\n".join(lines)

    def file(self, name: str) -> str:
        return f"{self.product.releases}/download/{name}"

    def downloads_table(self) -> str:
        w = WORDS[self.lang]
        rows = "".join(
            f'\n    <tr><th scope="row"><a href="{self.file(d["file"])}"><code>{d["file"]}</code></a></th><td>{d[self.lang]}</td></tr>'
            for d in self.product.downloads(self.site.shared_downloads))
        return (f'<div class="table-scroll" role="region" aria-labelledby="download-caption" tabindex="0">\n<table>\n'
                f'  <caption id="download-caption">{w["files"]}</caption>\n'
                f'  <thead><tr><th scope="col">{w["file"]}</th><th scope="col">{w["for"]}</th></tr></thead>\n'
                f"  <tbody>{rows}\n  </tbody>\n</table>\n</div>")

    def product_sheets(self) -> str:
        w = WORDS[self.lang]
        out = []
        for p in self.site.products.values():
            t, card = p.data[self.lang], p.data[self.lang]["card"]
            logo = p.data["logo"]
            imgs = "".join(
                f'<img class="logo-{theme}" src="@/assets/{p.id}/logo/{Path(logo[theme]).name}" alt="{t["name"]}" '
                f'width="{logo["width"]}" height="{logo["height"]}">' for theme in ("light", "dark"))
            shot = self.shot(card["shot"], "(max-width: 520px) 60vw, 240px", card["shot_alt"], "lazy", p,
                             f"@/assets/{p.id}/shots").replace("\n", "\n      ")
            platforms = "".join(f"<li>{x}</li>" for x in card["platforms"])
            out.append(f"""<article class="sheet" data-brand="{p.id}" style="--lines: {p.data.get("staff_lines", 5)}" aria-labelledby="sheet-{p.id}">
  <div class="sheet-text">
    <p class="sheet-logo">{imgs}</p>
    <h2 id="sheet-{p.id}">{card["title"]}</h2>
    <p>{card["does"]}</p>
    <dl>
      <dt>{w["made_for"]}</dt><dd>{card["for"]}</dd>
      <dt>{w["runs_on"]}</dt><dd><ul class="platforms">{platforms}</ul></dd>
    </dl>
    <div class="actions">
      <a class="button primary" href="@{p.id}/">{w["see"].format(name=t["name"])}</a>
      <a class="button outline" href="@{p.id}/download/">{w["download"]}</a>
    </div>
  </div>
  <div class="sheet-shot">
    <div class="phone-frame">
      {shot}
    </div>
  </div>
</article>""")
        return "\n".join(out)

    def macros(self, text: str) -> str:
        def run(m: re.Match) -> str:
            name, rest = m.group(1), m.group(2)
            args = dict(re.findall(r'([\w-]+)="([^"]*)"', rest))
            words = re.sub(r'[\w-]+="[^"]*"', "", rest).split()
            if name == "file":
                return self.file(words[0])
            if name == "releases":
                return self.product.releases
            if name == "data":
                if len(words) == 1 or words[1] in research.FORMATS:  # a named measurement: site/research.py
                    return research.macro(self, name, words, args)
                value = figures().lookup(words[0], words[1])
                return str(round(value * 100)) if args.get("as") == "percent" else str(value)
            if name == "figure":
                own = self.product.figures()
                draw = getattr(own, words[0], None) or getattr(figures(), words[0], None)
                if draw is None:
                    sys.exit(f"{self.dir}: no figure named {words[0]}")
                made = draw(self, **args)
            elif name == "shot":
                made = self.shot(words[0], args["sizes"], args["alt"], args.get("load", ""))
            elif name == "downloads":
                made = self.downloads_table()
            elif name == "products":
                made = self.product_sheets()
            elif name in research.MACROS:
                made = research.macro(self, name, words, args)
            else:
                sys.exit(f"{self.dir}: unknown macro {{{{{name}}}}}")
            # A block keeps the indentation of the line its macro stands on.
            before = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            return made.replace("\n", "\n" + before) if before.isspace() else made
        return re.sub(r"\{\{(\w+)([^{}]*)\}\}", run, text)

    # The download page, from the product's data --------------------------------------------
    def download_page(self) -> None:
        p, t = self.product, self.product.data[self.lang]
        d = t["download"]
        self.meta = {"title": d["title"], "description": d["description"], "main_class": "wrap downloads"}
        groups: dict[str, list[dict]] = {}
        for item in p.downloads(self.site.shared_downloads):
            groups.setdefault(item["group"], []).append(item)
        words = {**self.site.shared_groups[self.lang], **t.get("groups", {})}
        parts = [f'<h1>{d["heading"]}</h1>\n<p class="lead">{d["lead"]}</p>\n<div class="download-groups">']
        for group, items in groups.items():
            g = words[group]
            links = "".join(
                f'\n    <li><a class="button {"primary" if i == 0 else "outline"}" href="{self.file(x["file"])}">{x.get("label_" + self.lang, x["file"])}</a>'
                f'<span class="muted">{x[self.lang]}</span></li>' for i, x in enumerate(items))
            parts.append(f'<section id="{group}" aria-labelledby="{group}-title">\n  <h2 id="{group}-title">{g["title"]}</h2>\n'
                         f'  <ul class="download-files">{links}\n  </ul>\n  <p>{g["note"]}</p>\n</section>')
        parts.append(f'</div>\n<p class="muted">{d["more"]}</p>\n')
        self.body = "\n".join(parts)

    # The whole page ------------------------------------------------------------------------
    def render(self) -> str:
        p, t, w, site = self.product, self.product.data[self.lang], WORDS[self.lang], self.site
        if self.name == "download" and not self.body:
            self.download_page()
        other = "nb" if self.lang == "en" else "en"
        here = "" if self.name == "index" else self.name + "/"
        twin = (rel(self.dir, (posixpath.join(p.home(other), here).rstrip("/") or ".") + "/")
                if self.name in p.pages(other) else None)
        en = "./" if self.lang == "en" else twin
        head = [f'<title>{self.meta["title"]}</title>',
                f'<meta name="description" content="{self.meta["description"]}">',
                '<meta name="color-scheme" content="light dark">']
        for key in ("og_title", "og_description", "og_image"):
            if key in self.meta:
                head.append(f'<meta property="og:{key[3:]}" content="{self.meta[key]}">')
        if twin:
            head += [f'<link rel="alternate" hreflang="en" href="{en}">',
                     f'<link rel="alternate" hreflang="nb" href="{"./" if self.lang == "nb" else twin}">',
                     f'<link rel="alternate" hreflang="x-default" href="{en}">',
                     '<script src="@/lang.js"></script>']
        head.append(f'<link rel="icon" href="@/favicon.svg" type="image/svg+xml">')
        if "icons" in p.data:
            head += ['<link rel="icon" href="@/favicon.ico" sizes="any">',
                     '<link rel="apple-touch-icon" href="@/apple-touch-icon.png">']
        for css in [f'assets/{p.data["css"]}', "assets/fonts.css", "site.css", *self.named("styles"), *p.data.get("styles", [])]:
            head.append(f'<link rel="stylesheet" href="@/{css}">')
        for script in self.named("scripts"):
            head.append(f'<script type="module" src="@/{script}"></script>')

        if p.family:
            brand = f'<a class="brand brand-text" href="@lang/">{t["name"]}</a>'
            items = [(q.data[self.lang]["name"], f"@{q.id}/") for q in site.products.values()]
        else:
            logo = p.data["logo"]
            alt = t.get("logo_alt", w["home_alt"].format(name=t["name"]))
            logos = "".join(f'\n      <img class="logo-{theme}" src="@/assets/logo/{Path(logo[theme]).name}" alt="{alt}" '
                            f'width="{logo["width"]}" height="{logo["height"]}">' for theme in ("light", "dark"))
            brand = f'<a class="brand" href="@lang/">{logos}\n    </a>'
            items = t.get("nav", [])
        nav = []
        for label, href in items:
            link = self.links(f" {href}").strip()
            current = ' aria-current="page"' if link == "./" else ""
            nav.append(f'\n      <a href="{link}"{current}>{label}</a>')
        if twin:
            nav.append(f'\n      <a class="lang-switch" href="{twin}" hreflang="{other}" lang="{other}" data-lang-switch>{w["switch"]}</a>')
        family_bar = ""
        if site.family and not p.family:
            family = [f'<a href="@family/">{w["all"]}</a>']
            for q in site.products.values():
                current = ' aria-current="true"' if q is p else ""
                family.append(f'<a href="@{q.id}/"{current}>{q.data[self.lang]["name"]}</a>')
            family_bar = (f'<nav class="family-bar" aria-label="{w["family"]}">\n  <div class="wrap">\n    '
                          + "\n    ".join(family) + "\n  </div>\n</nav>\n")
        main_class = f' class="{self.meta["main_class"]}"' if "main_class" in self.meta else ""
        note = self.meta.get("footer", t.get("footer_note", ""))
        page = f"""<!doctype html>
<html lang="{self.lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {"\n  ".join(head)}
</head>
<body>
<a class="skip" href="#main">{w["skip"]}</a>

{family_bar}<header class="site-header">
  <div class="wrap">
    {brand}
    <nav class="site-nav" aria-label="{w["nav"]}">{"".join(nav)}
    </nav>
  </div>
</header>

<main id="main"{main_class}>
{self.body.rstrip()}
</main>

<footer class="site-footer">
  <div class="wrap">
    <span>{t["footer"]}</span>
    <span>{note}</span>
  </div>
</footer>
</body>
</html>
"""
        page = re.sub(r"[ \t]*<!--slot\b.*?-->\n?", "", page, flags=re.S)  # content slots are for authors
        return self.links(self.macros(page))


class Site:
    def __init__(self):
        conf = tomllib.loads((SITE / "shared" / "site.toml").read_text())
        self.shared_downloads = conf.get("downloads", [])
        self.shared_groups = {lang: conf[lang]["groups"] for lang in LANGS}
        every = [Product(f.parent, conf) for f in sorted(SITE.glob("*/product.toml"))]
        self.products = {p.id: p for p in every if not p.family}
        self.family = next((p for p in every if p.family), None)
        self.all = every
        mounts = [p.mount for p in every]
        if len(set(mounts)) != len(mounts):
            sys.exit("two products have the same mount")

    def copy_brand(self, p: Product, assets: Path, logo_dir: Path) -> None:
        web = p.brand / "dist" / "web"
        assets.mkdir(parents=True, exist_ok=True)
        shutil.copytree(web / "fonts", assets / "fonts", dirs_exist_ok=True)
        logo_dir.mkdir(parents=True, exist_ok=True)
        for logo in [p.data["logo"]["light"], p.data["logo"]["dark"], *p.data.get("marks", [])]:
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
            # Each product's folder holds everything its pages load, so it can move to a host of its own.
            for shared in ("site.css", "lang.js"):
                shutil.copy(SITE / "shared" / shared, out)
            for css in p.data.get("styles", []):
                if (p.dir / css).exists():  # the family's brands.css is made below
                    shutil.copy(p.dir / css, out)
            if "icons" in p.data:
                for icon in (p.brand / p.data["icons"]).iterdir():
                    shutil.copy(icon, out)
            else:
                shutil.copy(p.brand / p.data["favicon"], out / "favicon.svg")
            if (p.dir / "shots").exists():
                shutil.copytree(p.dir / "shots", out / "assets" / "shots")
            if (p.dir / "figures").exists():
                shutil.copytree(p.dir / "figures", out / "assets" / "data")
            if p.family:
                self.family_assets(out / "assets")
            for lang in LANGS:
                for name, source in p.pages(lang).items():
                    page = Page(self, p, lang, name, source)
                    # What a page names in its header: from the product's folder, else from site/shared.
                    for extra in page.named("styles") + page.named("scripts"):
                        found = [d / extra for d in (p.dir, SITE / "shared") if (d / extra).exists()]
                        if not found:
                            sys.exit(f"{page.dir}: {extra} is neither in {p.dir.name}/ nor in shared/")
                        shutil.copy(found[0], out)
                    target = OUT / page.dir / "index.html"  # a folder per page, so URLs have no .html
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(page.render())
        (OUT / ".nojekyll").touch()

    def family_assets(self, assets: Path) -> None:
        """The family page shows each product in its own brand: tokens scoped to [data-brand], fonts, logo, one shot."""
        css = []
        for p in self.products.values():
            web = p.brand / "dist" / "web"
            self.copy_brand(p, assets / p.id, assets / p.id / "logo")
            css.append((web / "fonts.css").read_text().replace('url("fonts/', f'url("{p.id}/fonts/'))
            css.append((web / p.data["css"]).read_text().replace(":root", f'[data-brand="{p.id}"]'))
            (assets / p.id / "shots").mkdir(exist_ok=True)
            for lang in LANGS:
                slot = p.data[lang]["card"]["shot"]
                for shot in (p.dir / "shots").glob(f"{slot}-*"):
                    shutil.copy(shot, assets / p.id / "shots")
        (assets / "brands.css").write_text("\n".join(css))


def check(out: Path) -> None:
    """Every local link and image in the built pages points at something that was built."""
    bad = []
    for page in out.rglob("index.html"):
        text = page.read_text()
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        for attr, value in re.findall(r'\b(href|src|srcset)="([^"]*)"', text):
            for url in ([u.split()[0] for u in value.split(", ")] if attr == "srcset" else [value]):
                if re.match(r"[a-z]+:", url):
                    continue
                path, _, frag = html.unescape(url).partition("#")
                target = (page.parent / path).resolve()
                if target.is_dir():
                    target = target / "index.html"
                if not target.exists() or out.resolve() not in target.parents:
                    bad.append(f"{page.relative_to(out)}: {url}")
                elif frag and target == page.resolve() and frag not in ids:
                    bad.append(f"{page.relative_to(out)}: no id for {url}")
    if bad:
        sys.exit("broken links:\n  " + "\n  ".join(bad))


if __name__ == "__main__":
    Site().build()
    check(OUT)
    print(f"site built in {OUT}")
