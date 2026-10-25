# Design tokens and the generator

One generator writes every brand's design for every platform. A brand is a token file and a folder for
its outputs; [`brands.json`](brands.json) lists them.

| File | What it is |
|---|---|
| [`build.py`](build.py) | The generator. No dependencies. |
| [`brands.json`](brands.json) | The brands: token file, output folder, contrast report. |
| [`neutral.json`](neutral.json) | The neutral roles: what every brand has, under one name. |
| [`icons.json`](icons.json) | The actions and their icon on each platform. One set for every brand so far. |
| [`tokens.json`](../brands/brasscribe/tokens/tokens.json) | Brasscribe's tokens (W3C Design Tokens, DTCG 2025.10). Fretscribe's are in [`../fretscribe/tokens/`](../brands/fretscribe/tokens/). |
| [`test_build.py`](test_build.py) | Checks on the tokens and on what is generated, for every brand. |

Run these from the repository root:

```sh
uv run design/tooling/build.py                     # write every brand's outputs
uv run design/tooling/build.py --check             # CI: exit 1 if any brand's output is stale
uv run design/tooling/build.py --brand fretscribe  # one brand
uv run --with pytest pytest design/tooling
uv run qa/tools/contrast.py --brands              # every brand, every mode; exit 1 on a failure or a stale report
                                                  # (a high-contrast mode needs 7:1 for every pair)
uv run qa/tools/contrast.py --brands --write      # rewrite the contrast reports
```

## What a brand gets

For each brand the generator writes `apple/`, `android/`, `windows/` and `web/` and an `icon-map.md`
into the brand's folder. The files carry the brand's name and its short prefix (`prefix` in its tokens):

| | Brasscribe (`design/brands/brasscribe/dist`) | Fretscribe (`design/brands/fretscribe/dist`) |
|---|---|---|
| Apple | `BrasscribeDesign.swift`, `BrasscribeDesign.xcassets`, `Fonts/` | `FretscribeDesign.swift`, `FretscribeDesign.xcassets`, `Fonts/` |
| Windows | `BrasscribeTheme.xaml` (`Bc…` keys), `BrasscribePinkTheme.xaml`, `Assets/Fonts/` | `FretscribeTheme.xaml` (`Fs…` keys), `Assets/Fonts/` |
| Web | `brasscribe.css` (`--scribe-…`, and `--bc-…` for its own), `fonts.css`, `icons.js`, `icons/`, `fonts/` | `fretscribe.css` (`--scribe-…`, and `--fs-…` for its own), `fonts.css`, `icons.js`, `icons/`, `fonts/` |
| Android | `no/kalli/scribe/design/ScribeTheme.kt`, `no/kalli/brasscribe/design/BrasscribeTheme.kt` and `BrasscribeIcon.kt`, `res/` | `no/kalli/scribe/design/ScribeTheme.kt`, `no/kalli/fretscribe/design/FretscribeTheme.kt` and `FretscribeIcon.kt`, `res/` |

The app icons in `dist/icons/` are not from this generator: each brand's `brand/build.py` renders them.

A brand's fonts are named in its tokens (`fonts`, by `font.family` key, with paths from the token file).
Each face is copied beside the platform's files with its licence text, under the names they have in the
brand's folder.

## The naming rule

Products share logic, not looks. So the names shared code may use are few, and everything else belongs
to a brand.

1. **Neutral names** are the same in every brand's generated files. They cover what any app needs:
   surfaces, text, edges, the two button fills, the accent, the brand colour, status, focus, ink, the ruled line and
   doubt, with the type ramp, spacing, radii, sizes and motion. They are generated
   under `Scribe…`: `ScribeTheme` and `ScribeColors` in Kotlin, `Color.Scribe`, `Font.Scribe` and
   `ScribeDesign` in Swift, `Scribe…Brush` in XAML, `--scribe-…` in CSS. Code that uses only these
   compiles against any brand.
2. **A brand's own names** hold what is the brand's own: `Color.Brasscribe.veryUncertain`,
   `FsUncertainTintBrush`, `--fs-tab-cursor-width`. Code that uses them belongs to that product.
3. **No neutral name carries one product's idea.** Staff, score, brass, string, tab, the ad lib and
   model colours, Pink and the notation metrics are never neutral. A product that wants the cursor or
   the loop colour reads its own brand's.
4. **A brand maps, it does not rename.** Where a brand's token has another name than the neutral role,
   its tokens say so under `$extensions.<brand>.neutral.roles`. A neutral role a brand neither has nor
   maps stops the generator.
5. **`brand` is identity, `accent` is for what you act on.** In every brand, `brand`, `brand-text` and
   `brand-tint` are the mark, the wordmark and brand moments (onboarding, empty states, About). They are
   never the colour of a link or a control. `accent` is the one colour beside the buttons that says
   "this does something": links. It is readable as text (4.5:1) on `bg`, `surface` and `surface-raised`
   in every mode, and each brand lists those pairs. A brand may give both the same hue; they are still
   two roles, so a brand whose identity colour cannot carry a link is not forced to use it for one.
   **A progress bar's fill is the brand colour**: it is not something to act on, `brand` passes 3:1 on
   every ground, and in a contrast theme `accent` is the system's link colour, which is wrong for a bar.
6. **A new neutral role** has to make sense for every brand, and every brand has to define it. A new
   role of one brand is added to that brand's tokens alone, with its system colour for Windows contrast
   themes and forced colours under `system-colours`.

### The colour roles

| Neutral role | Brasscribe's token | Fretscribe's token |
|---|---|---|
| `bg`, `surface`, `surface-raised` | the same | the same |
| `text`, `text-muted` | the same | the same |
| `border`, `border-strong` | the same | the same |
| `primary`, `on-primary`, `secondary`, `on-secondary` | the same | the same |
| `accent` | `brass-text` | `brand-text` (the blue ink) |
| `brand`, `brand-text`, `brand-tint` | `brass`, `brass-text`, `brass-tint` | the same |
| `success`, `warning`, `error` | the same | the same |
| `focus`, `scrim` | the same | the same |
| `ink` | the same | the same |
| `line` | `staff` | `string` |
| `uncertain` | the same | the same |

| The brand's own | Brasscribe | Fretscribe |
|---|---|---|
| Colour roles | `very-uncertain`, `adlib-tint`, `model-1` to `model-4`, `loop-tint`, `loop-edge`, `cursor`, `cursor-tint`, `selection-tint`, `selection-edge` | `uncertain-tint`, `loop-tint`, `loop-edge`, `cursor`, `cursor-tint`, `selection-tint`, `selection-edge` |
| Modes beside light, dark, high contrast and high contrast light | `pink`, `pink-dark` | none |
| Notation metrics (`notation` names the group) | `score` | `tab` |
| Type roles | the Studio ramp (`studio-*`) | none |
| Fonts | Instrument Serif | Atkinson Hyperlegible Next, Fretscribe Tab |
| Action icons (`BrasscribeIcon`, `FsIconPlay`, …) | the set of `icons.json` | the same set, under its own names |

Both brands have a cursor, a loop and a selection today. They stay with the brands: they are parts of a
score view and a tab view, which are two products' own screens. The action icons stay with the brands
too: `icons.json` is one set, and its actions are one product's so far (the talking score, the music
stand). The actions every app has (play, pause, settings) could get neutral names later, marked one by
one in `icons.json`.

### The names on each platform

| | Neutral | Brasscribe's own | Fretscribe's own |
|---|---|---|---|
| Kotlin | `ScribeTheme { }`, `ScribeTheme.colors.brand`, `ScribeColors`, `ScribeSpace`, `ScribeSize`, `ScribeMotion`, `ScribeShapes`, `ScribeButtonShape`, `scribeTypography()`, `ScribeNumericStyle` | `BrasscribeTheme(pink = …)`, `BrasscribeTheme.colors.veryUncertain`, `BrasscribeScore` | `FretscribeTheme`, `FretscribeTheme.colors.uncertainTint`, `FretscribeTab` |
| Swift | `Color.Scribe.brand`, `Font.Scribe.title1`, `ScribeDesign.Space.s4`, `ScribeDesign.Motion` | `Color.Brasscribe.cursor`, `BrasscribeDesign.Score`, `BrasscribePalette`, `BrasscribeIcon` | `Color.Fretscribe.uncertainTint`, `FretscribeDesign.Tab`, `Font.Fretscribe.tab(size:)` |
| XAML | `ScribeBrandBrush`, `ScribeBrandColor`, `ScribeSpace4`, `ScribeTitle1TextBlockStyle` | `BcCursorBrush`, `BcScoreCursorWidth`, `BcIconPlay` | `FsUncertainTintBrush`, `FsTabCursorWidth`, `FsTabFontFamily` |
| CSS | `--scribe-brand`, `--scribe-line`, `--scribe-space-4`, `--scribe-type-title-1-size` | `--bc-very-uncertain`, `--bc-cursor`, `--bc-score-cursor-width`, `--bc-type-studio-body-size`, `globalThis.BrasscribeIcons` | `--fs-uncertain-tint`, `--fs-tab-cursor-width`, `--fs-font-tab` |

### One name for each thing

A neutral role or scale has its neutral name and no other. A brand's prefix is only on what is the
brand's own, so code cannot read a neutral role under a brand's name.

- **The web: done.** `brasscribe.css` and `fretscribe.css` declare `--scribe-…` for what every brand
  has and `--bc-…` / `--fs-…` for the brand's own, in every mode. Where two neutral roles read one
  token (`accent` and `brand-text`), each has its own variable, and under forced colours each takes its
  own system colour.
- **Apple: done.** `Color.Scribe`, `Font.Scribe` and `ScribeDesign` are the declarations; `Color.Brasscribe`,
  `BrasscribeDesign.Score` and `Font.Fretscribe` hold only the brand's own. The colour sets of the asset
  catalog keep the names of the brand's tokens (`Brasscribe/brass`); `Color.Scribe.brand` reads that set.
  A brand's app adds its own type helpers to `Font.<Brand>`.
- **Windows: done.** The theme has `Scribe…` keys for the neutral roles, spacing, radii, sizes, motion,
  the display face and the type styles, and `Bc…` / `Fs…` keys for the brand's own colours, notation
  metrics, icons and other faces. The Pink dictionary has the same keys. In a contrast theme each key
  takes its role's system colour. Code that looks a key up by name fails only when it runs, so the
  Windows tests check every such name in both apps against the theme.
- **Android: done.** `ScribeColors`, `ScribeTheme` and the scales are the declarations, in
  `no.kalli.scribe.design`; a brand's package holds only its own. See [Android](#android).

### Android

The neutral theme is `no.kalli.scribe.design` (`ScribeTheme.kt`): the same declarations in every brand's
folder, with that brand's values. A brand's own is in its own package: `no.kalli.brasscribe.design` has
`BrasscribeColors` (its own roles), `BrasscribeScore` and `BrasscribeTheme`, which wraps `ScribeTheme`
and chooses Pink; `no.kalli.fretscribe.design` has `FretscribeColors` (with `uncertainTint`), `FretscribeTab`
and `FretscribeTheme`. An app is built with one brand's folder.

The two Android apps still share screens that draw with a product's own colours (a score's cursor, the
very uncertain "?"). Those screens do not read a brand's type: each product hands the colours in
(`ProductColors` in `apps/android`, given by `Product.Theme`).

The action icons' drawables are `ic_bc_…` in every brand's folder: both apps' screens name them, so the
resource names wait for the screens to be split by product.

Brasscribe's links are plain text colour with an underline today; its `accent` is the brass that
carries text, and the site's link hover uses it. Fretscribe's `accent` is what it called `brand` for
links; the value is the same blue ink. Both fill their progress bars with `brand`.

## What stops the generator

A brand that lacks something is told what, when the generator starts: a brand in `brands.json` without
a name, token file or folder, or sharing one with another brand; a prefix that is `scribe` or another
brand's; a mode without colours; a role missing from a mode; a neutral role with no token; a role of the
brand's own without a system colour; no `notation` group; no `fonts.display`, or a font file that is not
there.

## Adding a brand

1. Write its `tokens.json`: every colour role in `light`, `dark`, `high-contrast` (on a dark ground, for a
   dark appearance with more contrast) and `high-contrast-light` (on a light ground, for a light one), and under `$extensions.<brand>`: `modes`, `contrast`, `prefix`, `neutral`
   (only the roles it names differently), `notation`, `system-colours` for its own roles, and `fonts`
   (the display face with its `android-resource`, its name in `res/font`).
2. Add it to `brands.json` with its own output folder.
3. Run the generator and `qa/tools/contrast.py --brands --write`. The tests and CI pick the brand up
   from `brands.json`.
