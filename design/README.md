# Brasscribe design

This folder is the single source for how Brasscribe Play and Studio look, sound and behave.
- [`system.md`](system.md): components, patterns, layout, navigation and the screen map
- [`brand/brand.md`](brand/brand.md): name, mark, icon, typeface, voice and copy rules
- [`mockups/png/`](mockups/png/): the key screens (phone and desktop, light and dark, one in Norwegian, and Studio)

![Home, What is this?, review and score](mockups/png/home-desktop-light.png)

## Principles

1. **Easy before impressive.** A brass-band player of any age should be able to finish without help: one decision per screen, one primary button, and words from the band room.
2. **Calm is the premium.** Warm paper and ink, generous space, one serif for headings, and brass used sparingly. Nothing flashes, bounces or competes with the music.
3. **The score owns colour.** The accessibility palette (uncertain, very uncertain, loop, cursor) appears only on the notation. Everything around it is neutral.
4. **Never colour alone.** Every state carries a shape or a word as well: "?", a boxed "?", dashed bars, a bold part name.
5. **Native first, brand second.** Use each platform's own controls, fonts, icons and navigation. The brand shows only through the tokens, the button shape, the display face and the mark.
6. **Honest and on your side.** Say what the app is unsure of, and give every error a way forward. Recordings stay on your own devices.

## Tokens

- **Source:** [`tokens/tokens.json`](tokens/tokens.json), in W3C Design Tokens (DTCG 2025.10) format.
  - Colour roles are sibling groups `color.light`, `color.dark` and `color.high-contrast`.
  - Typography roles name their Dynamic Type style, Material role and Windows ramp style.
- **Icons:** [`tokens/icons.json`](tokens/icons.json) lists every action with its en and nb label and its SF Symbol, Material Symbol and Segoe Fluent glyph.

```sh
uv run design/tokens/build.py            # regenerate design/dist and docs/accessibility/design-tokens.json
uv run design/tokens/build.py --check    # CI: exit 1 if anything is stale
uv run --with pytest pytest design/tokens
uv run qa/tools/contrast.py --tokens design/tokens/tokens.json   # 67 pairs x 3 themes, exit 1 on failure
uv run design/brand/build.py             # mark, lockups, app icons (needs rsvg-convert)
node design/mockups/render.mjs           # mockup PNGs (Playwright from studio/node_modules, or PLAYWRIGHT_MODULE=…)
```

**Contrast:** all 201 pairs pass. See [`qa/reports/contrast-design-tokens.md`](../qa/reports/contrast-design-tokens.md).

**Accessibility compatibility:**
- `docs/accessibility/design-tokens.json` is generated from these tokens in its existing shape. The score hues are unchanged; the neutrals are warmer.
- Its report, [`qa/reports/contrast-tokens.md`](../qa/reports/contrast-tokens.md), shows 84 of 84 pairs passing.

### Using the tokens per platform

The app teams copy (or link) from `design/dist/`. The generator never edits `apps/`.

| Platform | Copy | Use |
|---|---|---|
| Apple | `dist/apple/BrasscribeDesign.xcassets`, `BrasscribeDesign.swift`, `Fonts/InstrumentSerif-Regular.ttf` (add it to `UIAppFonts` / `ATSApplicationFontsPath`), and `dist/icons/apple/AppIcon.appiconset` into the app's asset catalog | `Color.Brasscribe.primary`, `Font.Brasscribe.display`, `BrasscribeDesign.Space.s4`, `BrasscribeDesign.Motion.animation(reduceMotion:)`, `BrasscribeIcon.loop.systemName`. The colour sets carry dark and high-contrast appearances. |
| Android | `dist/android/kotlin/no/brasscribe/design/*.kt`, `dist/android/res/drawable/ic_bc_*.xml`, `res/font/instrument_serif.ttf`, and `dist/icons/android/res/**` (the launcher icons) | `BrasscribeTheme(display = FontFamily(Font(R.font.instrument_serif))) { … }`, `BrasscribeTheme.colors.uncertain`, `BrasscribeButtonShape`, `painterResource(R.drawable.ic_bc_play)` |
| Windows | `dist/windows/BrasscribeTheme.xaml` → `Themes/`, `Assets/Fonts/…`, and `dist/icons/windows/Assets/*` | Merge the dictionary into `App.xaml`. Use `{ThemeResource BcTextBrush}`, `{StaticResource BcTitle1TextBlockStyle}`, `FontIcon Glyph="{StaticResource BcIconPlay}"`. Contrast themes use the user's system colours. |
| Studio | `dist/web/brasscribe.css` (+ `fonts.css`, `studio-compat.css`, `icons.js`, `icons/*.svg`) and `dist/icons/web/*` | `var(--bc-text)`. Handles `data-theme`, dark mode, `prefers-contrast`, `forced-colors` and `prefers-reduced-motion`. |

## Implementation checklist

These are the changes each app team needs to make. The ones marked **(drift)** are places where the app today differs from the agreed accessibility spec.

### All apps
- [ ] Replace the hand-copied colours with the generated tokens (Apple `Color.Brasscribe.*`, Android `BrasscribeTheme`, Windows `BrasscribeTheme.xaml`).
- [ ] Mark uncertainty with a "?" above the note, and a boxed "?" below 0.4, in the note colour. Remove rings, diamonds and brackets. **(drift)**
- [ ] Use one primary button per screen, with 12 px corners. No pill shapes and no platform accent colour.
- [ ] Use the display face only for screen titles of 28 pt and up and for the wordmark.
- [ ] Put the app icon from `dist/icons/<platform>` in place.
- [ ] Put the copy through the voice rules in `brand/brand.md`, and use the glossary for both en and nb. Rename "companion engine" and "motor" to "Brasscribe on your computer" / "Brasscribe på datamaskinen".
- [ ] Give every error a title, a reason and a recovery button (`mockups/png/error-*`).
- [ ] Follow the player-bar order: Play first, bar fields for the loop, a beat counter that never flashes, and "Mute my part".
- [ ] Transcribing shows the plain-language steps, the percentage and the time left, and Cancel. Announce at most every 10% or 10 s.
- [ ] Check reduced motion, 200% text and high contrast against the mockups.

### Apple (`apps/apple`)
- [ ] `FlowViews.swift`: change "Uncertain notes are marked with an open diamond and an orange colour." to the "?" legend. **(drift)**
- [ ] `NotationView.swift`: draw the "?" / boxed "?" instead of the open diamond. **(drift)**
- [ ] Align "This decides how the music is taken apart…" with the other platforms' "Your answer decides how Brasscribe listens. It never guesses."
- [ ] Home: `NavigationSplitView` with the library in the sidebar on iPad and macOS; one primary Import button; the other ways in as list rows.
- [ ] Make the pairing copy command-free (the command moves under "Details for the band's tech person").
- [ ] The player bar tint becomes `Color.Brasscribe.primary`, not the system blue.

### Android (`apps/android`)
- [ ] `strings.xml` and `values-nb`: `legend_uncertain` and `legend_very_uncertain` (rings and brackets) become the "?" legend. **(drift)**
- [ ] `NoteGlyph.kt`: draw the "?" mark instead of the rings. **(drift)**
- [ ] Theme: switch from `PlayTheme` to `BrasscribeTheme` (not dynamic colour). The primary purple `#6B3FA0` is the score **cursor** colour and must not be used for buttons. **(drift)**
- [ ] Home: one filled button instead of three.
- [ ] nb: use "Gjenta" consistently (not "Repetisjon"), and "På datamaskinen din" (not "motoren").
- [ ] Use the adaptive icon with the monochrome layer.

### Windows (`apps/windows`)
- [ ] Merge `BrasscribeTheme.xaml`, and retire the colour keys in `Themes/Tokens.xaml`.
- [ ] Use `NavigationView` with the library, and a `Frame` for the flow steps.
- [ ] Replace the `Assets/` logos with `dist/icons/windows/Assets/*`, including the unplated target sizes.
- [ ] Use `FontIcon` glyphs from `BcIcon*`, and `PathIcon` for the custom metronome and count-in glyphs.

### Studio (`studio/`)
- [ ] Load `brasscribe.css` and then `studio-compat.css`, and delete the colour blocks in `styles.css`.
- [ ] Put the lockup in the header, the favicon set in place, and the page title in the display face.
- [ ] Map the piano-roll colours onto `model-1` to `model-4`, and keep the patterns.

## Open questions

1. Do brass-band players read "?" and a boxed "?" as "check this note"? This is carried over from `docs/accessibility/visual-design-tokens.md`.
2. On Apple, *Increase Contrast* in light mode switches to the dark high-contrast palette, as the accessibility spec says. A light high-contrast variant may suit low-vision users in light mode better; test it with users.
3. Instrument Serif at 28 pt with Dynamic Type AX sizes: confirm on a device that the relative scaling to `largeTitle` stays readable.
4. The Windows XAML is checked for well-formed XML only; it has not been compiled with WinUI on this machine (no Windows).
