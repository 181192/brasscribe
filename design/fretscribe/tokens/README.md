# Fretscribe tokens

`tokens.json` uses the same W3C Design Tokens (DTCG 2025.10) schema and role names as Brasscribe's
[`design/tokens/tokens.json`](../../tokens/tokens.json), with `brand*` in place of `brass*`, `string`
in place of `staff` and a `tab` group in place of `score`. It has no ad lib, model or Pink roles. Its
contrast pairs live under `$extensions."no.fretscribe".contrast`.

Run these from the repository root:

```sh
uv run design/tokens/build.py --tokens design/fretscribe/tokens/tokens.json --out design/fretscribe/dist --only android
uv run design/tokens/build.py --tokens design/fretscribe/tokens/tokens.json --out design/fretscribe/dist --only android --check
uv run qa/tools/contrast.py --tokens design/fretscribe/tokens/tokens.json > design/fretscribe/tokens/contrast.md
```

## The Android theme

The Android app is one code base built as two products, so Fretscribe's generated theme
([`../dist/android`](../dist/android)) has the same Kotlin names as Brasscribe's (`BrasscribeTheme`,
`BrasscribeColors.brass`, `BrasscribeSpace` and so on) with Fretscribe's values.
`$extensions."no.fretscribe".android` says where each name the theme needs and Fretscribe lacks comes
from:

| The theme's name | Fretscribe's token |
|---|---|
| `brass`, `brass-text`, `brass-tint` | `brand`, `brand-text`, `brand-tint` |
| `staff` | `string` |
| `very-uncertain` | `uncertain` (the tab has one level of doubt) |
| `adlib-tint` | `loop-tint` |
| `model-1` to `model-4` | `ink` (Studio's data series; no Fretscribe screen uses them) |
| the `pink` and `pink-dark` palettes | `light` and `dark` |
| the `score` group | `tab`; `single-part-reflow-zoom` keeps Brasscribe's value |

`display-font` names the title face, Atkinson Hyperlegible Next, and the weight its titles are set in
(600, as in [`brand.md`](../brand/brand.md)); the app gets it as `res/font/display`. A name that is
neither in the tokens nor in this map stops the generator. `uncertain-tint` has no name in the shared
theme yet, so it is not generated.

## Contrast check

`qa/tools/contrast.py` exits 1 on any failure, and the tests in `qa/tools/tests` run it on these tokens.
The current report is [`contrast.md`](contrast.md): 0 failures in light, dark, high contrast and high
contrast light.
