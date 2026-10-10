# Design tokens and the generator

One generator writes every brand's design for every platform. A brand is a token file and a folder for
its outputs; [`brands.json`](brands.json) lists them.

| File | What it is |
|---|---|
| [`build.py`](build.py) | The generator. No dependencies. |
| [`brands.json`](brands.json) | The brands: token file, output folder, contrast report. |
| [`neutral.json`](neutral.json) | The neutral roles: what every brand has, under one name. |
| [`icons.json`](icons.json) | The actions and their icon on each platform. One set for every brand so far. |
| [`tokens.json`](tokens.json) | Brasscribe's tokens (W3C Design Tokens, DTCG 2025.10). Fretscribe's are in [`../fretscribe/tokens/`](../fretscribe/tokens/). |
| [`test_build.py`](test_build.py) | Checks on the tokens and on what is generated, for every brand. |

Run these from the repository root:

```sh
uv run design/tokens/build.py                     # write every brand's outputs
uv run design/tokens/build.py --check             # CI: exit 1 if any brand's output is stale
uv run design/tokens/build.py --brand fretscribe  # one brand
uv run --with pytest pytest design/tokens
uv run qa/tools/contrast.py --brands              # every brand, every mode; exit 1 on a failure or a stale report
uv run qa/tools/contrast.py --brands --write      # rewrite the contrast reports
```

## What a brand gets

For each brand the generator writes `apple/`, `android/`, `windows/` and `web/` and an `icon-map.md`
into the brand's folder. The files carry the brand's name and its short prefix (`prefix` in its tokens):

| | Brasscribe (`design/dist`) | Fretscribe (`design/fretscribe/dist`) |
|---|---|---|
| Apple | `BrasscribeDesign.swift`, `BrasscribeDesign.xcassets`, `Fonts/` | `FretscribeDesign.swift`, `FretscribeDesign.xcassets`, `Fonts/` |
| Windows | `BrasscribeTheme.xaml` (`Bc…` keys), `BrasscribePinkTheme.xaml`, `Assets/Fonts/` | `FretscribeTheme.xaml` (`Fs…` keys), `Assets/Fonts/` |
| Web | `brasscribe.css` (`--scribe-…`, and `--bc-…` for its own), `fonts.css`, `icons.js`, `icons/`, `fonts/` | `fretscribe.css` (`--scribe-…`, and `--fs-…` for its own), `fonts.css`, `icons.js`, `icons/`, `fonts/` |
| Android | `BrasscribeTheme.kt`, `BrasscribeIcon.kt`, `ScribeTheme.kt`, `res/` | the same file names (see [Android](#android)) |

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
5. **`brand` is identity, `accent` is for what you act on or follow.** In every brand, `brand`,
   `brand-text` and `brand-tint` are the mark, the wordmark and brand moments (onboarding, empty states,
   About). They are never the colour of a link, a control or a state. `accent` is the one colour beside
   the buttons that says "this does something" or "this is where it is": links and the progress bar. It
   is readable as text (4.5:1) on `bg`, `surface` and `surface-raised` in every mode, and each brand
   lists those pairs. A brand may give both the same hue; they are still two roles, so a brand whose
   identity colour cannot carry a link is not forced to use it for one.
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
| Kotlin | `ScribeTheme { }`, `ScribeTheme.colors.brand`, `ScribeColors`, `ScribeSpace`, `ScribeSize`, `ScribeMotion`, `ScribeShapes`, `ScribeButtonShape`, `scribeTypography()`, `ScribeNumericStyle` | `BrasscribeTheme`, `BrasscribeColors.veryUncertain`, `BrasscribeScore` | see [Android](#android) |
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
- **Android: not yet.** There Brasscribe's names still hold every role, and the neutral names are other
  names for them.

### Android

The two Android apps are one code base today, and its screens use `BrasscribeTheme` and
`BrasscribeColors`. So every brand's Android theme is still written under those names, through the map
in `$extensions.<brand>.android` ([`../fretscribe/tokens/README.md`](../fretscribe/tokens/README.md)),
and `ScribeTheme.kt` adds the neutral names on top. `ScribeColors` is another name for
`BrasscribeColors` until the screens are split by product; then each brand's theme is generated under
its own names like on the other platforms, and Fretscribe's own roles (`uncertain-tint`) get a place on
Android.

Brasscribe's links are plain text colour with an underline today, and its progress bar is brass
(`design/system.md`). Its `accent` is the brass that carries text. Fretscribe's `accent` is what it
called `brand` for links and the progress bar; the value is the same blue ink.

## What stops the generator

A brand that lacks something is told what, when the generator starts: a brand in `brands.json` without
a name, token file or folder, or sharing one with another brand; a prefix that is `scribe` or another
brand's; a mode without colours; a role missing from a mode; a neutral role with no token; a role of the
brand's own without a system colour; no `notation` group; no `fonts.display`, or a font file that is not
there.

## Adding a brand

1. Write its `tokens.json`: every colour role in `light`, `dark`, `high-contrast` and
   `high-contrast-light`, and under `$extensions.<brand>`: `modes`, `contrast`, `prefix`, `neutral`
   (only the roles it names differently), `notation`, `system-colours` for its own roles, and `fonts`.
2. Add it to `brands.json` with its own output folder.
3. Run the generator and `qa/tools/contrast.py --brands --write`. The tests and CI pick the brand up
   from `brands.json`.
