# The public site

One build makes the pages of every product and the family page that presents them together.

```sh
site/build.sh && python3 -m http.server -d site/_site 8000
```

`site/build.sh` checks that nothing names a version, then runs `site/build.py` (Python's standard
library only), which also fails on a link or an image that points at nothing.

## Where things are served

| Folder in the built site | What |
|---|---|
| `/` | Brasscribe, where its pages have always been (`/guide/`, `/research/`, `/download/`, `/nb/…`) |
| `/fretscribe/` | Fretscribe (`/fretscribe/guide/`, `/fretscribe/download/`, `/fretscribe/nb/…`) |
| `/apps/` | The family page: the apps side by side and what they share |

Every link in the built pages is relative, and each product's folder holds everything its pages
load (its stylesheets, fonts, icons and screenshots). So the whole site works under any path or
host, and a product's folder can be served as the root of a host of its own. When a product moves
to its own host, set `url` in its `product.toml`: the other products' links to it then go there.

## What is where

- `shared/`: `site.css` (the layout and components of every product page, written against the
  `--scribe-…` design tokens every brand has), `lang.js` (the language choice), `site.toml` (where
  release files come from, and the release files every product lists), `make_shots.py`.
- `<product>/`: `product.toml` (where it is served, its brand, its logo, its menu, its release
  files, and its sheet on the family page), `pages/<lang>/<page>.html`, `shots.txt` and `shots/`,
  and any stylesheet of its own (named under `styles`).
- `family/`: the family page. Its product sheets are made from each product's `[<lang>.card]`.

A page file is the inside of `<main>` under a header of `key: value` lines (`title`,
`description`, and optionally `og_title`, `og_description`, `og_image`, `main_class`, `footer`).
`index.html` is the product's front page; any other name is served at `<name>/`. The download page
is made from the product's `[[downloads]]` unless the product has a `download.html` of its own.
`site/build.py`'s first lines list the link roots (`@/`, `@lang/`, `@family/`, `@<product>/`) and
the macros (`{{shot}}`, `{{file}}`, `{{releases}}`, `{{downloads}}`).

## Figures and numbers

A front page's figures are drawn at build time from files in the repository, so a page shows what the
engine answered and no number is typed into a page:

- `{{figure <name> …}}` calls a function in `shared/figures.py` (or in the product's own `figures.py`):
  the strip under the headline, the steps from sound to written music, the tab viewer, a measured rate
  as squares of a hundred, the device table. Their words are in `figures.py` and in the product's
  `product.toml` (`[[<lang>.stages]]`, `[<lang>.tabdemo]`, `[[platforms]]`).
- `{{data <file> <path/to/value> as="percent"}}` prints a number from a JSON file, such as a gated
  rate in `eval/baselines.json`.
- A page names the stylesheets and scripts it needs in its header (`styles:`, `scripts:`); the build
  copies them from the product's folder or from `shared/`. `shared/showcase.css` and `showcase.js`
  belong to the figures. Every figure is complete without the script, which only adds what moves.
- `<product>/figures/` is served as `assets/data/`. Fretscribe's is made by
  `uv run --with numpy python site/fretscribe/make_demo.py`: `tab-demo.json` asks the core's solver
  for each tuning the viewer offers, and `guitar-line-sound.json` is the loudness of the take the
  engine heard, made again by the fixture's own script and checked against the job's audio id.
  Run it again when the guitar fixture or the solver changes.

## Adding a product

1. `site/<product>/product.toml`: copy Fretscribe's and change it. `brand` points at the product's
   folder in `design/brands/`, whose generated web tokens give the pages their colours and type.
2. `site/<product>/shots.txt`, then `uv run --with pillow python site/shared/make_shots.py <product>`.
3. `site/<product>/pages/en/` and `pages/nb/`: `index.html` and `guide.html`.

The product then has its pages, its download page, its place in the bar above every page and its
sheet on the family page.

## Research pages and figures

A product's research page (`pages/<lang>/research.html`) types no number. It names a measurement and
the build prints it: from `eval/baselines.json` (the numbers `scribe bench` gates), from
`convert/reports/` (the converted models' benchmarks), or from `shared/research/measured/measured.toml`
(numbers measured once that exist only in prose under `docs/`, each with its source and command). So
the page follows the baselines. `site/research.py` lists the keys and the macros: `{{data <key> [format]}}`
(the same macro as above, given a measurement's name instead of a file), `{{span}}`, `{{holds}}`,
`{{chart}}`, `{{pipeline}}` and `{{part}}`.

- **A sentence that depends on a number says so.** `{{holds <key> < 0.5}}` prints nothing and fails the
  build when it stops being true; a figure's `holds` does the same for its title. When the build fails
  there, the numbers have moved past what the words say: rewrite the words, then the rule.
- **Figures** are described in `shared/research/figures.py` (words in English and Norwegian, rows that
  name their measurements). The build writes each as a data table with its numbers; `shared/charts.js`
  draws the chart from the same numbers and folds the table away, so the table is also what a browser
  without scripts shows. The exact values of a row appear in a panel under the plot on hover, touch
  and keyboard focus. `shared/charts.css` holds the series colours, which were checked for colour
  blindness on each brand's page colour, light and dark. A page that shows a figure names both files in
  its header (`styles: charts.css`, `scripts: charts.js`); any page may.
- **The spread behind a mean** (a dot per piece) comes from `shared/research/measured/per-piece.json`,
  made by `shared/research/per_piece.py` on a machine with the eval data. The build fails when a spread's
  mean no longer matches its baseline, so run the script again with a deliberate baseline change.
- **Parts** in `shared/research/<lang>/` are shared by the products' research pages.
- **The keyboard is tested in a browser** by `shared/research/tests/keyboard.mjs` (its first lines say how
  to run it): every row of every view of every chart is reached with the arrow keys, and Escape clears
  the readout. Run it after a change to `shared/charts.js`. The build itself refuses one known cause of a
  dead keyboard: a part of a chart stored under the name of one of the chart's methods.

## Download links

No page names a version or writes a release URL. Pages use `{{file <name>}}` and `{{releases}}`,
and `releases` in `shared/site.toml` says where they point. When a product gets releases of its
own, give it its own `releases` in its `product.toml`; nothing else changes.

## Content that waits for a release

A comment that starts `<!--slot` marks where content goes once a feature has shipped. The build
leaves these comments out of the pages.
