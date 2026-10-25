# Fretscribe tokens

`tokens.json` uses the same W3C Design Tokens (DTCG 2025.10) schema and role names as Brasscribe's
[`design/brands/brasscribe/tokens/tokens.json`](../../brasscribe/tokens/tokens.json), with `brand*` in place of `brass*`, `string`
in place of `staff` and a `tab` group in place of `score`. It has no ad lib, model or Pink roles. Its
contrast pairs live under `$extensions."no.kalli.fretscribe".contrast`.

Run these from the repository root:

```sh
uv run design/tooling/build.py --brand fretscribe
uv run design/tooling/build.py --brand fretscribe --check
uv run qa/tools/contrast.py --brands --write    # rewrites contrast.md (and Brasscribe's report)
```

## What is generated

[`../../tokens/README.md`](../../../tooling/README.md) describes the generator and the naming rule. For
Fretscribe it writes into [`../dist`](../dist):

- `apple/`: `FretscribeDesign.swift` (`Color.Fretscribe`, `Font.Fretscribe`, `FretscribeDesign`) and
  `FretscribeDesign.xcassets`;
- `windows/`: `FretscribeTheme.xaml` with `Fs…` keys;
- `web/`: `fretscribe.css` with `--fs-…` variables, `fonts.css`, the icons;
- `android/`: `ScribeTheme.kt` and Fretscribe's own `FretscribeTheme.kt` (below).

Each of them also has the neutral names (`Color.Scribe.brand`, `ScribeBrandBrush`, `--scribe-brand`,
`ScribeTheme.colors.brand`), the same as in Brasscribe's files. `$extensions."no.kalli.fretscribe"` holds what
the generator needs beside the tokens: `prefix` (`fs`), `neutral` (the ruled line is `string` here, and
the neutral `accent`, for links and the progress bar, is `brand-text`; `brand` is identity only),
`notation` (the `tab` group), `system-colours` for Fretscribe's own roles and `fonts`.

The fonts are Atkinson Hyperlegible Next (titles; a variable font, used at weight 600) and Fretscribe
Tab (fret numbers). Both are copied to `apple/Fonts`, `windows/Assets/Fonts` and `web/fonts` with their
licence texts. No Apple or Windows app uses these files yet.

## The Android theme

Fretscribe's Android files ([`../dist/android`](../dist/android)) are the neutral theme,
`no.kalli.scribe.design` with Fretscribe's values, and Fretscribe's own in `no.kalli.fretscribe.design`:
`FretscribeColors` (`uncertainTint`, the cursor, loop and selection colours), `FretscribeTab` (the tab's
metrics) and `FretscribeTheme`. The tokens no longer say how Fretscribe passes for Brasscribe.

The Fretscribe app still has screens from Brasscribe that draw a score. What they need of a product's
own, the app gives them (`Fretscribe.Theme` in `apps/android/products/fretscribe`): the one doubt colour
where a score has a very doubtful one, the repeat's band where it has a band for freely played bars.

`fonts.display` names the title face, Atkinson Hyperlegible Next, and its name in `res/font`
(`android-resource`); the app gets it as `res/font/display`, set in the weight of the `display`
typography token (600, as in [`brand.md`](../brand/brand.md)).

## Contrast check

`qa/tools/contrast.py` exits 1 on any failure, and the tests in `qa/tools/tests` run it on these tokens.
The current report is [`contrast.md`](contrast.md): 0 failures in light, dark, high contrast and high
contrast light. In the two high-contrast modes every pair has to reach 7:1.
