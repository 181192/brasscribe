# Fretscribe tokens

`tokens.json` uses the same W3C Design Tokens (DTCG 2025.10) schema and role names as Brasscribe's
[`design/tokens/tokens.json`](../../tokens/tokens.json), with `brand*` in place of `brass*`, `string`
in place of `staff` and a `tab` group in place of `score`. It has no ad lib, model or Pink roles. Its
contrast pairs live under `$extensions."no.fretscribe".contrast`.

Run these from the repository root:

```sh
uv run design/tokens/build.py --brand fretscribe
uv run design/tokens/build.py --brand fretscribe --check
uv run qa/tools/contrast.py --brands --write    # rewrites contrast.md (and Brasscribe's report)
```

## What is generated

[`../../tokens/README.md`](../../tokens/README.md) describes the generator and the naming rule. For
Fretscribe it writes into [`../dist`](../dist):

- `apple/`: `FretscribeDesign.swift` (`Color.Fretscribe`, `Font.Fretscribe`, `FretscribeDesign`) and
  `FretscribeDesign.xcassets`;
- `windows/`: `FretscribeTheme.xaml` with `Fs…` keys;
- `web/`: `fretscribe.css` with `--fs-…` variables, `fonts.css`, the icons;
- `android/`: the theme under the names the shared screens use (below).

Each of them also has the neutral names (`Color.Scribe.brand`, `ScribeBrandBrush`, `--scribe-brand`,
`ScribeTheme.colors.brand`), the same as in Brasscribe's files. `$extensions."no.fretscribe"` holds what
the generator needs beside the tokens: `prefix` (`fs`), `neutral` (the ruled line is `string` here, and
the neutral `accent`, for links and the progress bar, is `brand-text`; `brand` is identity only),
`notation` (the `tab` group), `system-colours` for Fretscribe's own roles and `fonts`.

The fonts are Atkinson Hyperlegible Next (titles; a variable font, used at weight 600) and Fretscribe
Tab (fret numbers). Both are copied to `apple/Fonts`, `windows/Assets/Fonts` and `web/fonts` with their
licence texts. No Apple or Windows app uses these files yet.

## The Android theme

The Android app is one code base built as two products, so Fretscribe's generated theme
([`../dist/android`](../dist/android)) has the same Kotlin names as Brasscribe's (`BrasscribeTheme`,
`BrasscribeColors.brass`, `BrasscribeSpace` and so on) with Fretscribe's values, and the neutral names
in `ScribeTheme.kt` beside them. `$extensions."no.fretscribe".android` says where each name the theme
needs and Fretscribe lacks comes from:

| The theme's name | Fretscribe's token |
|---|---|
| `brass`, `brass-text`, `brass-tint` | `brand`, `brand-text`, `brand-tint` |
| `staff` | `string` |
| `very-uncertain` | `uncertain` (the tab has one level of doubt) |
| `adlib-tint` | `loop-tint` |
| `model-1` to `model-4` | `ink` (Studio's data series; no Fretscribe screen uses them) |
| the `pink` and `pink-dark` palettes | `light` and `dark` |
| the `score` group | `tab`; `single-part-reflow-zoom` keeps Brasscribe's value |

`display-font` names the title face, Atkinson Hyperlegible Next; the app gets it as `res/font/display`,
set in the weight of the `display` typography token (600, as in [`brand.md`](../brand/brand.md)). A name that is
neither in the tokens nor in this map stops the generator. `uncertain-tint` has no name in the shared
theme, so it is not generated for Android; it is in the Apple, Windows and web files.

## Contrast check

`qa/tools/contrast.py` exits 1 on any failure, and the tests in `qa/tools/tests` run it on these tokens.
The current report is [`contrast.md`](contrast.md): 0 failures in light, dark, high contrast and high
contrast light.
