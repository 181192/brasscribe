# The public site

One build makes the family home and every app's pages.

```sh
site/build.sh && python3 -m http.server -d site/_site 8000
```

`site/build.sh` checks that nothing names a version, then runs `site/build.py` (Python's standard
library only). The build fails on a link, an image or an anchor that points at nothing, on words
missing in one of the two languages, and on words a page has but does not use.

## Where things are served

| Address | What |
|---|---|
| `/` | The family home: both apps at work, which one is for whom, what they share |
| `/brasscribe/`, `/fretscribe/` | An app's front page |
| `/<app>/guide/`, `/<app>/download/`, `/<app>/how-it-works/` | The same pages, at the same names, for every app |

Every page has one address, in both languages (below). Every link in the built pages is relative,
and each app's folder holds what its pages load, so the site works under any path or host.
Addresses the site had before (`/guide/`, `/research/`, `/apps/`, every `/nb/…`) are kept as small
pages that send the visitor on, to the same place on the page (`#…`); they are listed under
`[redirects]` in `shared/site.toml`.

The bar's colours, the family's mark and the family home's palette are the family's own look,
made from the brands' by `design/tooling/family.py` (`design/brands/scribe/`).

### The site's host

`base` in `shared/site.toml` is the one place that says where the site is served
(`https://scribe.kalli.app/`); canonical links and shared previews are made from it, and no page
holds an absolute address of its own. The host itself is not a file in the build: the site is
deployed by the `pages` workflow, so the custom domain is the repository's setting (Settings ›
Pages › Custom domain, with "Enforce HTTPS"), and the domain's DNS has a `CNAME` record for the
host that points at `<owner>.github.io`. GitHub then sends the old address on to the new host, and
the small pages listed under `[redirects]` do the rest for paths that have moved. To move the site
again, change the DNS record, the repository setting and `base`.

## One address, two languages

A page is its structure and its words, kept apart:

- `pages/<name>.html` is structure only. An empty element with `data-t="key"` takes the words of
  that key; `data-t-<attribute>="key"` gives an attribute (`aria-label`, `alt`) its words.
- `pages/<name>.en.toml` and `pages/<name>.nb.toml` hold the page's words, over the app's
  `text.<lang>.toml` (its menu, footer, download page), over `shared/text.<lang>.toml` (the bar,
  the figures). A table in a file (`[hero]`, `lead = …`) is the key `hero.lead`.
- The build writes the page in English and an `nb.json` beside it. `shared/scribe.js` chooses the
  language (`?lang=nb` or `?lang=en` in the address, then what was chosen before, then the
  browser's), swaps the words where they stand, sets `<html lang>` and the title, and remembers the
  choice, also one that came with the address. What a figure or a screenshot shows differently in
  Norwegian is swapped as a whole, and the scripts that draw things are told (`scribe:lang` on
  `document`). The reader stays at the same heading, and a figure keeps what its controls stood at
  (`remember` in `shared/showcase.js`). Without JavaScript the page
  is in English and says so.
- A number or a reference that a macro prints in the structure (`{{data …}}` in a table cell) and that
  reads differently in Norwegian (0.66, 0,66) is swapped where it stands, like a word.
- A page may still be one whole file per language (`pages/en/<name>.html` and
  `pages/nb/<name>.html`): its Norwegian body is swapped in whole. No page is.

## What is where

- `shared/`: `site.css` (the family bar, the app's row of pages, the base of every page),
  `showcase.css` and `showcase.js` (the figures), `scribe.js` and `early.js` (the language),
  `product.html` (the one structure of every app's front page), `figures.py`, `text.<lang>.toml`,
  `site.toml` (where the site and the release files are, the old addresses), `make_shots.py`,
  `take_tools.py`.
- `<app>/`: `product.toml` (brand, logo, release files, what each device does, which measured
  rates to show), `text.<lang>.toml`, `pages/`, `shots.txt` and `shots/`, its brand stylesheet
  (`brass.css`, `ruled-paper.css`), `take/` and `figures/` (below), and `figures.py` when its
  music is drawn differently from a tab.
- `family/`: the family home, with the same parts.

The site has three levels, with the same names everywhere: **Scribe** (the line, the home at `/`),
its **apps** (Brasscribe, Fretscribe; a new app is a new folder), and each app's **devices** (the
app for Android, iPhone and iPad, Mac and Windows, and the programs on the computer: Bandroom, and
Studio where an app has it). The bar at the top is the way down and back up, the same on every
page: Scribe › its apps, with the one you are in marked, and the language. Under it each app has the same row: Overview,
Guide, Download, How it works. The family home shows the line first and the apps as its members;
every app's front page has the same "on your devices" section, one card for each entry of
`[[platforms]]` in its `product.toml` (what it does by itself, what it needs Bandroom for, where
to get it); the download page has a part for each device with its files. The footer of every page
names the line and its apps.

What only a script can work (a figure's buttons) carries the class `await-js`: it has its room on
the page from the start and is shown when the script has made it work, so nothing moves while the
page loads. An app's `preload` in `product.toml` names the font files of its headline.

## An app's front page

Every app's front page is `shared/product.html`: the same parts in the same order (a hero that
performs, what you get, see it work, try it, what you need, how sure it is, get it). An app gives
it its words (`pages/index.<lang>.toml`), its brand, and its figures under the same names: `hero`,
`steps`, `viewer`, `rates`, `devices`, `gets`, `screens`.

## Figures, recordings and numbers

A front page's figures are drawn at build time from files in the repository, so a page shows what
the engine answered and no number is typed into a page:

- `{{figure <name> …}}` calls a function in `shared/figures.py`, or in the app's own `figures.py`.
  Every figure is complete without the script, which only adds what moves.
- `{{data <file> <path/to/value> as="percent"}}` prints a number from a JSON file, such as a gated
  rate in `eval/baselines.json`; an app's `[[rates]]` name the rates its front page shows.
- Each app's figures come from a **take**: a short real recording, written down by the real
  engine. `<app>/take/` holds what the engine answered, `<app>/figures/` what the pages load (the
  recording as a small mp3, its loudness, the engraved parts or the tab's tunings), served as
  `assets/data/`. `<app>/make_take.py` makes both from the dataset: it checks the source's
  SHA-256 and the excerpt's samples, runs the engine, and writes the files; `--keep` makes the
  figures again from the committed `take/`. Its first lines say what it needs. The site's build
  needs none of it.

  | App | Recording | Run |
  |---|---|---|
  | Brasscribe | ChoraleBricks v1.1.0, CC BY 4.0: a brass quartet, the opening of a Bach chorale | `uv run --with verovio --with numpy python site/brasscribe/make_take.py` |
  | Fretscribe | GuitarSet, CC BY 4.0: a guitarist picking the Canon progression | `uv run --with numpy python site/fretscribe/make_take.py` |

## Adding an app

1. `site/<app>/product.toml`: copy Fretscribe's and change it. `brand` points at the app's folder
   in `design/brands/`, whose generated web tokens give the pages their colours and type.
2. `site/<app>/shots.txt`, then `uv run --with pillow python site/shared/make_shots.py <app>`.
3. A take (`make_take.py`), and `figures.py` if its music is not a tab.
4. `text.<lang>.toml`, `pages/index.<lang>.toml` (the words of the front page) and a guide.

The app then has its front page, its download page, its place in the bar and its strip on the
family home (add its part to `family/pages/index.html`).

## Download links

No page names a version or writes a release URL. Pages use `{{file <name>}}` and `{{releases}}`,
and `releases` in `shared/site.toml` says where they point. When an app gets releases of its own,
give it its own `releases` in its `product.toml`; nothing else changes.

## Content that waits for a release

A comment that starts `<!--slot` marks where content goes once a feature has shipped. The build
leaves these comments out of the pages.

## Research pages and figures

A product's research page (`pages/research.html`, with its words in `research.en.toml` and
`research.nb.toml` like every page) types no number. It names a measurement and
the build prints it: from `eval/baselines.json` (the numbers `scribe bench` gates), from
`convert/reports/` (the converted models' benchmarks), or from `shared/research/measured/measured.toml`
(numbers measured once that exist only in prose under `docs/`, each with its source and command). So
the page follows the baselines. `site/research.py` lists the keys and the macros: `{{data <key> [format]}}`
(the same macro as above, given a measurement's name instead of a file), `{{span}}`, `{{holds}}`,
`{{chart}}`, `{{pipeline}}` and `{{part}}`.

- **A sentence that depends on a number says so.** `{{holds <key> < 0.5}}` prints nothing and fails the
  build when it stops being true; a figure's `holds` does the same for its title. When the build fails
  there, the numbers have moved past what the words say: rewrite the words, then the rule.
- **Figures** are described in `shared/research/figures.py` (rows that name their measurements, and
  the keys of their words). The words are in `shared/research/words.en.toml` and `words.nb.toml`:
  `[chart]` what every figure says, `[figure.<name>]` one figure's title, caption, labels and notes.
  The two files must hold the same keys, and a key nothing uses fails the build. Numbers are written
  the way the language writes them, in the figure, its table and its readout. The build writes each as a data table with its numbers; `shared/charts.js`
  draws the chart from the same numbers and folds the table away, so the table is also what a browser
  without scripts shows. The exact values of a row appear in a panel under the plot on hover, touch
  and keyboard focus. `shared/charts.css` holds the series colours, which were checked for colour
  blindness on each brand's page colour, light and dark. A page that shows a figure names both files in
  its header (`styles: charts.css`, `scripts: charts.js`); any page may.
- **The spread behind a mean** (a dot per piece) comes from `shared/research/measured/per-piece.json`,
  made by `shared/research/per_piece.py` on a machine with the eval data. The build fails when a spread's
  mean no longer matches its baseline, so run the script again with a deliberate baseline change.
- **Parts** (`shared/research/measure-<name>.html`, shown with `{{part measure-<name>}}`) are shared by
  the products' research pages. A part is structure like a page; its words are under
  `[measure.<name>]` in the same two word files.
- **The keyboard is tested in a browser** by `shared/research/tests/keyboard.mjs` (its first lines say how
  to run it): every row of every view of every chart is reached with the arrow keys, and Escape clears
  the readout, in English, after a change to Norwegian, after the change back and on a first visit in
  Norwegian; in each, every figure must be drawn once and in the page's language. Run it after a change
  to `shared/charts.js`, `shared/scribe.js` or how the build writes a figure. The build itself refuses one known cause of a
  dead keyboard: a part of a chart stored under the name of one of the chart's methods.
- **A paper keeps to the conventions of its field**, and the build checks what it can: citations are
  `{{cite <key>}}` from `shared/research/references.toml` (numbered in the order of first citation;
  an unknown key, or an entry no paper cites, fails the build), and `{{references}}` prints the list;
  figures, tables and equations are numbered separately and referred to with `{{ref fig:<name>}}`,
  `{{ref table:<name>}}` and `{{ref eq:<name>}}` (a figure or table that the text has not referred to
  before it appears fails the build); `{{built}}` prints the date and commit of the checkout; the
  abstract (`<p class="abstract-text">`) must be 150 to 250 words in each language. Where the pieces behind a mean are
  known, figures, tables and `{{data <key>@sd}}`, `@lo`, `@hi` give the standard deviation and a
  bootstrap 95 % interval. Add a reference only after checking it against its DOI or record page.
