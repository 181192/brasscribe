# 04 — Brand directions

Fretscribe records or opens audio and writes it down as tablature, with optional standard notation, for guitar, bass, ukulele and mandolin. It is free, non-commercial and local-first, and it must meet WCAG 2.2 AA. This document scans the visual landscape, proposes three brand directions, recommends one, and specifies the logo files in `design/brand/`.

Method notes. Competitor observations come from homepages, app-store listings and design write-ups (see Sources). They describe patterns, not measured colours. All contrast ratios are computed with the WCAG 2.x relative-luminance formula. Font claims were checked against the font files from the `google/fonts` repository: digit advance widths and OpenType features were inspected, and the digits were rendered at 44–80 px and again under a 3 px Gaussian blur to approximate reading from a music stand.

---

## 1. Landscape: clichés to avoid, gaps to own

### Clichés

| Pattern | Where it shows up | Why Fretscribe should avoid it |
|---|---|---|
| **Game loops**: streaks, stars, levels, high scores | Yousician ("Earn rewards, beat high scores, and level up"), Fender Play's "Streaks" | Fretscribe is a tool, not a course. Game loops teach people to "play the app" (a common Yousician criticism) and suggest engagement metrics that a no-cloud app doesn't have. |
| **AI-magic claims**: "within seconds", "unparalleled accuracy", purple/blue gradient glow | Klangio Guitar2Tabs ("your transcriptions have unparalleled accuracy"), Moises ("world-class Hi-Fi models") | Transcription is often wrong about *where* a note is played, even when the pitch is right. Overclaiming breaks trust the first time a beginner learns a wrong fingering. |
| **Catalogue bragging and upsell** | Ultimate Guitar ("1M+ songs catalog"), Songsterr Plus (print, speed and loop behind a paid plan), free-trial CTAs everywhere (Guitar Pro, Yousician, Klangio's 20-second demo) | Fretscribe has no catalogue and nothing to sell. Pricing-page layouts and "Go Pro" badges would be dishonest. |
| **Rock-poster styling**: black and neon, flames, headstocks, stage photography, celebrity endorsements | Common across the category; Moises features testimonials from Charlie Puth and Slipknot's drummer | It excludes the teacher, the ukulele player and the beginner, and it dates quickly. |
| **Colour-only meaning**: green = right, red = wrong, rainbow chord colours | Tuners (Chordify's tuner line "turns green"), chord-colour UIs | Fails WCAG 1.4.1 and is invisible to about 1 in 12 men with colour-vision deficiency. |
| **Cloud as the default verb**: "Upload your track", "paste a YouTube link" | Moises, Klangio | It contradicts local-first. Fretscribe's verbs are *record* and *open*. |
| **Staff lines treated as decoration** (pale hairlines) | A requirement to design against, not a measured observation | Staff lines carry meaning (which string), so they are graphical objects under WCAG 1.4.11 and need 3:1 against the background. |

### Gaps a calm, honest, tool-like brand can own

1. **Honest uncertainty.** None of the marketing reviewed foregrounds *doubt*. Klangio only notes that accuracy is best "when the audio quality is good". A brand that shows confidence and alternatives ("this could be 7th fret on G or 2nd on B") is new, and it is also better teaching.
2. **Privacy you can see.** Moises promises it will "never train on your data", but processing still happens in its cloud. "Nothing leaves this device" as a visible, verifiable brand value is unclaimed.
3. **Music-stand legibility.** Soundslice is the closest to a calm, print-quality reading tool; its redesign principles are "make things more approachable and obvious" and "optimize the common cases". No one brands *legibility itself*: numerals you can read from a stand one metre away, with unambiguous 1/7, 0/8 and 6/8/9.
4. **Instrument-neutral.** The category defaults to six-string electric-guitar culture. Bass, ukulele and mandolin players are an afterthought. A brand built on "lines and numbers" covers all four instruments naturally.
5. **Free without strings.** There are no trial banners, locked buttons or ads. The calm is the proof.

---

## 2. Three directions

All three share these non-negotiables:

- Uncertainty is never shown by colour alone. It always carries a shape (a dashed outline plus a "?" affordance) and a text alternative.
- Text meets 4.5:1 (1.4.3) and UI components meet 3:1 (1.4.11).
- Motion honours `prefers-reduced-motion`, and tab that scrolls during playback can be paused (2.2.2).
- Controls are at least 24 × 24 CSS px (2.5.8), and the scrub bar has a non-drag alternative such as step buttons or time entry (2.5.7).
- Sticky transport bars never cover the focused element (2.4.11).

### Ruled Paper

**Concept.** Fretscribe is a careful notebook: ink on ruled paper, where the lines are strings and the app writes down what it hears and pencils in what it isn't sure of.

**Personality.** Calm, plain-spoken, precise. It sounds like a good teacher: explains once, never gushes, and admits doubt. It uses short sentences and says "not sure" rather than "low confidence".

| Moment | Microcopy |
|---|---|
| Onboarding | "Play something, or open a recording. Fretscribe writes it down as tab, on this device, and marks anything it isn't sure of." |
| Unsure note | "Not sure about this one. The pitch is clear, but it could be 7th fret on the G string or 2nd fret on the B string. Listen to the bar and pick the one that suits your hand." |
| Empty library | "Nothing written down yet. Record a riff or open an audio file to start." |
| Error | "Couldn't read this file. It looks like a video with no sound track. Export the audio as WAV, MP3 or M4A and try again." |

**Logo idea: "Strummed strings".** Six horizontal bars on a rounded-square tile. The bars get thicker from top to bottom, as the strings do (tab puts the high string on top). A slanted gap cuts through all six, rising from bottom-left to top-right. It reads three ways: as a downstroke across the strings (in tab the low string, at the bottom, sounds first), as a pen stroke, and as the place where fret numbers sit (in tab, a number interrupts its line). Details are in §4.

**Palette.**

| Role | Light | Dark |
|---|---|---|
| Background (paper) | `#FAF8F3` | `#15171A` |
| Surface (cards, sheet) | `#FFFFFF` | `#1F2226` |
| Ink: text, fret numbers | `#1B1D21` | `#ECEAE4` |
| Ink 2: secondary text | `#4B5058` | `#A9AEB6` |
| Rule: tab lines, dividers, input borders | `#7A808A` | `#7F858F` |
| Accent: actions, links, focus, playhead | `#1F5FAD` (blue ink) | `#8AB8F2` |
| Unsure: stroke and text | `#9A5200` (umber) | `#F2B24C` |
| Unsure: tint behind the numeral (20 % amber over surface) | `#FCF0DB` | `#493F2E` |
| Error | `#B3261E` | `#FF8A80` |

Measured contrast:

| Pair | SC | Light | Dark |
|---|---|---|---|
| Ink on background / surface | 1.4.3 | 15.90 / 16.88 | 14.93 / 13.27 |
| Ink 2 on background / surface | 1.4.3 | 7.65 / 8.12 | 8.05 / 7.16 |
| Fret number over its line knockout (ink on surface) | 1.4.3 | 16.88 | 13.27 |
| Rule on background / surface | 1.4.11 | 3.75 / 3.98 | 4.84 / 4.30 |
| Accent on background / surface (links, icons) | 1.4.3 | 6.00 / 6.37 | 8.74 / 7.77 |
| Button label on accent (white / `#15171A`) | 1.4.3 | 6.37 | 8.74 |
| Unsure stroke or text on background / surface | 1.4.3, 1.4.11 | 5.53 / 5.86 | 9.62 / 8.55 |
| Ink numeral on unsure tint | 1.4.3 | 14.97 | 8.58 |
| Unsure stroke on tint (inside) | 1.4.11 | 5.20 | 5.53 |
| Solid amber `#F2B24C` on background (why it is not used as a fill) | — | **1.76 (fails)** | — (ink on it: 1.55, fails) |
| Error on background / surface | 1.4.3 | 6.16 / 6.54 | 7.87 / 7.00 |
| Focus ring (accent) on background / surface | 1.4.11 | 6.00 / 6.37 | 8.74 / 7.77 |

Solid amber fails as a background in both themes: against light paper, and under the light dark-mode ink. So the unsure mark is a *20 % tint* behind the normal ink numeral (pencil, not highlighter), and its boundary is always the dashed stroke (`#9A5200` light, `#F2B24C` dark), which passes against both the tint inside and the surface outside. The focus ring shares the accent hue, so on accent buttons it sits outside a 2 px background-coloured offset. The ring then touches only background or surface, both of which pass. Blue and umber are distinguishable under all three common colour-vision deficiencies. Amber and error red may not be, but error never appears inside the tab, and every state also carries a shape.

**Typography.**

- **UI:** Atkinson Hyperlegible Next (OFL 1.1), a variable font from 200 to 800. Use 400 for body text and 600 for headings. It was designed by the Braille Institute for low-vision readers and covers more than 150 languages.
- **Fret numbers:** Atkinson Hyperlegible Mono (OFL 1.1) at 600, with `font-feature-settings: "zero"`. **This is inverted from the usual behaviour:** the default zero in this face has a reverse slash, and the `zero` feature turns it into a plain oval 0. Tab uses 0 constantly for open strings, so a plain 0 keeps the page quiet, and the 8 already differs from it by its pinched waist. Checked in the files: the 1 has a flag and a base (it can't be read as 7 or l), the 7 has a plain straight stroke, the 6 and 9 have open, straight tails that separate them from 8, and 0 versus 8 survives a 3 px blur. The face is monospaced, so the figures are tabular.
- **Standard notation:** Bravura or Leland (SMuFL music fonts, OFL).

**Iconography.** 24 px grid, 1.75 px stroke, round caps and joins, no fills except for a selected state. Glyphs borrow the mark's grammar (horizontal lines plus one decisive stroke). "Unsure" gets its own icon: a dashed circle with "?". There are no guitar-headstock pictograms.

**Motion.** Motion only explains. The playhead moves linearly in time with the audio. UI transitions take 120–200 ms with ease-out and no overshoot. A newly transcribed bar fades in left to right, like writing. There's no confetti, no bounce and no pulsing "AI" shimmer. Under `prefers-reduced-motion` the playhead jumps bar by bar and fades become instant.

---

### Workbench

**Concept.** Fretscribe is a luthier's bench: warm wood, nickel fret wire and good light, somewhere to take a song apart and learn how it's built.

**Personality.** Warm, encouraging, hands-on. It sounds like a friendly mentor and uses "we".

| Moment | Microcopy |
|---|---|
| Onboarding | "Bring a song you want to learn. We'll lay it out on the fretboard for you, right here on your phone." |
| Unsure note | "This one's a judgement call. The pitch is clear, but it fits in two places on the neck. We've picked the closer one; tap to try the other." |
| Empty library | "Your bench is clear. Record something, or open a file you've been meaning to learn." |
| Error | "That file didn't open. It may be damaged, or in a format we can't read yet (we take WAV, MP3, M4A and FLAC)." |

**Logo idea: "Fret and inlay".** A horizontal rounded rectangle representing a fingerboard segment, 3:2 aspect. Four thin string lines run through it lengthwise (four so the mark suits every supported instrument), crossed by one vertical fret wire in nickel grey, twice the string weight, set at 40 % of the width. A single round inlay dot sits centred in the space to the right of the wire. The wordmark is "Fretscribe" in Source Serif 4 Semibold, sentence case.

**Palette.**

| Role | Light | Dark |
|---|---|---|
| Background (maple) | `#F6EFE3` | `#1C1512` (rosewood) |
| Surface | `#FFFBF4` | `#28201B` |
| Ink | `#2B1E18` | `#F3E9DA` |
| Ink 2 | `#5E4E44` | `#C2B4A3` |
| Rule (nickel) | `#8B7D72` | `#8E8177` |
| Accent (abalone teal) | `#1E6F6A` | `#6CC4BC` |
| Unsure stroke / tint | `#8C5A00` / `#F7EAD0` | `#E6B85C` / `#4E3E28` |
| Error | `#A8321F` | `#FF9580` |

| Pair | SC | Light | Dark |
|---|---|---|---|
| Ink on background / surface | 1.4.3 | 14.12 / 15.64 | 15.00 / 13.32 |
| Ink 2 on background / surface | 1.4.3 | 6.94 / 7.68 | 8.88 / 7.89 |
| Rule on background / surface | 1.4.11 | 3.48 / 3.86 | 4.77 / 4.23 |
| Accent on background / surface; button label on accent | 1.4.3 | 5.19 / 5.76; 5.94 | 8.80 / 7.82; 8.80 |
| Unsure stroke on background / surface | 1.4.11 | 5.14 / 5.69 | 9.76 / 8.67 |
| Ink on unsure tint | 1.4.3 | 13.55 | 8.55 |
| Unsure stroke on tint | 1.4.11 | 4.93 | 5.57 |
| Error on background / surface | 1.4.3 | 5.85 / 6.48 | 8.46 / 7.51 |

**Typography.**

- **Display:** Source Serif 4 (OFL), optical sizes.
- **UI:** Source Sans 3 (OFL). Its figures are tabular by default (every digit is 472 units wide).
- **Fret numbers:** IBM Plex Sans (OFL). Its digits are tabular by default (all 600 units wide), the 0 is plain, the 1 has a flag and a base, and 0/8 survives the blur test. Source Sans 3 is not used for tab because its 1 has no base.
- **Standard notation:** Leland or Bravura.

**Iconography.** A 2 px stroke with slightly rounded corners. Duotone is allowed, with a 20 % tint fill, for empty states. There are small craft details, such as a fret wire or an inlay dot, as accents. There are no wood textures in the UI: the warmth comes from colour only.

**Motion.** Gentle and physical, 200–260 ms with a soft ease-in-out. A selected string "settles" with a 2 px damped offset, and sheets slide in like a drawer. Reduced motion removes the settle and the slide.

**Risk.** Wood and brown sits close to "vintage guitar shop" and Americana clichés. The warm paper palette also leaves less room for a clear unsure colour, because the umber and the ink are both brown-leaning.

---

### Field Recorder

**Concept.** Fretscribe is a precise pocket instrument, like a field recorder or a cockpit display: matte graphite, one signal orange, labels you can read at a glance.

**Personality.** Terse and exact. Every word is a label, and it uses symbols and numbers where it can. The risk is that beginners find it cold. The rule is that a terse label is always followed by a plain sentence where a decision is needed.

| Moment | Microcopy |
|---|---|
| Onboarding | "Record → Tab. Processed on this device. Nothing uploaded." |
| Unsure note | "Low confidence: 2 positions. G string, 7th fret / B string, 2nd fret. Select to hear each." |
| Empty library | "No takes yet. Record or import." |
| Error | "Import failed: no audio stream. Supported: WAV, MP3, M4A, FLAC." |

**Logo idea: "Meter tab".** A square with six horizontal bars of different lengths, left-aligned like a level meter, one per string. On the fourth bar a single orange square cell sits where a fret number would be. The wordmark is "FRETSCRIBE" in B612 Bold, all caps, with +4 % tracking.

**Palette.** Dark-first.

| Role | Light | Dark |
|---|---|---|
| Background | `#EFEEEA` | `#121314` |
| Surface | `#FAFAF8` | `#1D1E20` |
| Ink | `#141516` | `#E9E7E2` |
| Ink 2 | `#50545A` | `#A2A6AC` |
| Rule | `#7C8087` | `#7A7E85` |
| Signal (actions, record, playhead) | `#B33A00` | `#FF7A33` |
| Unsure stroke / tint | `#8A5A00` / `#FBEBC6` | `#FFC24D` / `#4A3F29` |
| Error | `#B00020` | `#FF8A8A` |
| Focus | `#141516` (ink ring) | `#FF7A33` |

| Pair | SC | Light | Dark |
|---|---|---|---|
| Ink on background / surface | 1.4.3 | 15.75 / 17.49 | 15.05 / 13.50 |
| Ink 2 on background / surface | 1.4.3 | 6.56 / 7.29 | 7.61 / 6.82 |
| Rule on background / surface | 1.4.11 | 3.42 / 3.80 | 4.56 / 4.09 |
| Signal on background / surface; button label on signal | 1.4.3 | 5.14 / 5.71; 5.96 | 7.16 / 6.42; 7.16 |
| Unsure stroke on background / surface | 1.4.11 | 5.11 / 5.67 | 11.58 / 10.39 |
| Ink on unsure tint | 1.4.3 | 15.50 | 8.35 |
| Unsure stroke on tint | 1.4.11 | 5.02 | 6.43 |
| Error on background / surface | 1.4.3 | 6.31 / 7.01 | 8.20 / 7.35 |
| Focus ring on background; on signal button | 1.4.11 | 15.75; 3.07 | 7.16; offset needed |

**Typography.** B612 and B612 Mono (OFL). They were designed for Airbus cockpit displays for legibility under stress, which makes a good music-stand story. B612's digits are all the same width (1300 units), and both faces have a plain 0 and a 1 with a flag and a base. The limits are only two weights (regular and bold) and narrower language coverage than Atkinson Next.

**Iconography.** 2 px stroke with square caps. The icons are strictly geometric pictograms, always paired with a text label, in the style of hardware silkscreen.

**Motion.** Mechanical: linear or stepped, no easing overshoot. Meters and the playhead move in discrete steps and panels cut rather than slide. Reduced motion needs very little change.

**Risk.** Orange on graphite now reads as generic "pro audio gear". Dark-first UIs drift towards the black-and-neon cliché, and the terse voice fights the beginner audience.

---

## 3. Recommendation: Ruled Paper

1. **It is built on the product's one honest differentiator.** "Ink for what we heard, pencil for what we're not sure of" gives uncertainty a native visual language: an umber dashed outline and a faint tint on paper. It doesn't have to be bolted onto a gamer or pro-audio aesthetic.
2. **It serves the whole audience.** Paper and ink is neutral across age, instrument and genre. A beginner, a gigging bassist and a mandolin teacher all recognise a notebook.
3. **It has the strongest accessibility story, and it is verified.** Atkinson Hyperlegible Next for the UI and Atkinson Hyperlegible Mono (plain zero) for tab make legibility itself the brand. Every text pair passes 4.5:1 in both themes, and the staff lines pass 3:1.
4. **The mark comes from tab itself** (strings of graded gauge, the gap where numbers sit, the strum direction), and it stays legible from 16 px to 1024 px.
5. **It prints.** Teachers will print tab. A paper-first palette gives a black-and-white print that looks the same as the screen.

Workbench is the fallback if user testing finds Ruled Paper too austere. Borrow Workbench's warmer voice for onboarding only; Ruled Paper's voice already allows warmth.

---

## 4. Logo files (Ruled Paper)

All files are in `design/fretscribe/brand/`. The text is outlined to paths, so no font is needed at runtime. Each file has `role="img"` and a `<title>`, and each passes `xmllint --noout`.

| File | Use |
|---|---|
| `logo-mark.svg` | Primary mark: ink tile `#1B1D21`, paper strings `#FAF8F3` (15.9:1) |
| `logo-mark-dark.svg` | On dark backgrounds: paper tile `#ECEAE4`, ink strings `#15171A` |
| `favicon-16.svg` | Pixel-hinted 16 × 16 version: whole-pixel bars, a staircase gap, `crispEdges`. Use for favicons at 16 and 32 px. |
| `app-icon-fullbleed.svg` | Square, full-bleed, **no baked corner radius**. iOS applies its own mask. The art is scaled to 78 % of the tile, which suits iOS and store listings. **Android adaptive icons need a separate foreground with the art scaled to 64 %.** At 78 % the corners of the outer strings sit 36.6 % from the centre, outside the 66/108 dp safe circle (radius 30.6 %). At 64 % they sit at 30 %. |
| `wordmark.svg`, `wordmark-dark.svg` | "fretscribe", lowercase, Atkinson Hyperlegible Next at 600 (a static instance of the variable font), −8/1000 em tracking |
| `lockup.svg`, `lockup-dark.svg` | Mark and wordmark together. The mark runs from the baseline up to the ascender (760/1000 em), with a 0.36 × mark-height gap before the text. |

**Construction of the mark** (48 × 48 grid):

- **Tile:** 48 × 48 with an 11 corner radius.
- **Strings:** six bars from x = 9 to x = 39, centres 6 apart and centred vertically at y = 9, 15, 21, 27, 33 and 39. Heights run from top (high string) to bottom (low string): 1.6, 2.0, 2.4, 2.8, 3.2 and 3.6.
- **Gap:** a parallelogram 5.5 wide, centred at x = 24 where y = 24, with a slope of 0.55 horizontal per unit of rise, cut from every bar. It rises to the right.
- **Hinted 16 px version:** rows 2, 4, 6, 8 and 10 are 1 px high and the bottom string (rows 12–13) is 2 px. Columns 3–12 are filled, with 2 px gaps starting at columns 10, 9, 8, 7, 6 and 5 from top to bottom.

**Rendering checks.** Both marks were rendered at 16, 32, 48, 180 and 512 px, and the 16 and 32 px renders were inspected upscaled with nearest-neighbour. Scaled down automatically, the 48-grid mark turns into a grey tile at 16 px, which is why the hinted favicon exists. The hinted version keeps a clear diagonal at 16 px. At 32 px and above the scalable mark reads well. With graded string thickness and a slanted *gap* (negative space rather than a drawn line), the mark reads as strummed strings. Two rejected versions made this clear: equal-weight bars with a stepped gap read as a text-document icon, and a drawn slash read as a strike-through.

**Clear space and minimum size.** Keep clear space equal to a quarter of the mark's height on every side. Use the scalable mark at 24 px and above and `favicon-16.svg` below that. Show the wordmark on its own only at 12 px cap height or more.

---

## 5. Implementation notes

> **Changed in the design** (`design/fretscribe/brand/brand.md`): the unsure mark is a "?" above the tab column rather than a dashed outline round the numeral (outlines read as circled numbers in tab); focus is ink, not the accent; the tab font ships with the plain zero built in as "Fretscribe Tab"; and the platform UI face is used for body text, with Atkinson Hyperlegible Next for titles.

- **Self-host the fonts and bundle them in the apps.** Don't load them from the Google Fonts CDN at runtime. A third-party request conflicts with "local-first, nothing leaves the device", and subsetting CDNs can drop the `zero` and `tnum` features the tab renderer depends on.
- **Respect the OFL naming rule.** Atkinson Hyperlegible's reserved font names apply to modified versions, and subsetting counts as modification. Either ship the unmodified OFL files, or rename any subset family (for example to `FS Tab Mono`) and keep the licence file alongside it.
- **Tab renderer defaults:**
  - `font-feature-settings: "zero"` (a plain 0, in this face only) and 600 weight.
  - Numerals at least 1.5× the body size.
  - The line behind a number is knocked out with the surface colour.
  - Two-digit frets are drawn with −4 % tracking so "12" stays within a column.
- **Unsure note:** a `#9A5200` / `#F2B24C` 1.5 px dashed rounded outline around the numeral, a `#FCF0DB` / `#493F2E` tint behind it with the numeral in normal ink, a "?" badge, and an accessible name such as "7, G string, not sure: alternative 2 on B string".

---

## Sources

- Songsterr, About: https://www.songsterr.com/about
- Songsterr on the App Store: https://apps.apple.com/us/app/songsterr-tabs-chords/id399211291
- No Treble, "Songsterr: A Look at the Tab Player for iOS and Android": https://www.notreble.com/buzz/2013/01/21/songsterr-a-look-at-the-tab-player-for-ios-and-android/
- Guitar Pro homepage: https://www.guitar-pro.com/
- Ultimate Guitar homepage: https://www.ultimate-guitar.com/
- Klangio Guitar2Tabs: https://klang.io/guitar2tabs/
- Klangio homepage: https://klang.io/
- Moises homepage: https://moises.ai/
- Soundslice, "Introducing our player redesign": https://www.soundslice.com/blog/224/introducing-our-player-redesign/
- Yousician homepage: https://yousician.com/
- American Songwriter, Yousician review: https://americansongwriter.com/yousician-review/
- Guitar World, "Fender Play vs Yousician": https://www.guitarworld.com/features/fender-play-vs-yousician
- JustinGuitar homepage: https://www.justinguitar.com/
- Chordify on Google Play: https://play.google.com/store/apps/details?id=net.chordify.chordify&hl=en&gl=US
- Guitar Chalk, Chordify review: https://www.guitarchalk.com/chordify-review/
- Braille Institute, Atkinson Hyperlegible Next and Mono launch: https://www.brailleinstitute.org/about-us/news/braille-institute-launches-enhanced-atkinson-hyperlegible-font-to-make-reading-easier/
- Atkinson Hyperlegible Mono on Google Fonts: https://fonts.google.com/specimen/Atkinson+Hyperlegible+Mono
- anthesis, "Font comparison and review: Atkinson Hyperlegible Mono": https://www.anthes.is/font-comparison-review-atkinson-hyperlegible-mono.html
- Google Fonts repository (font files and OFL licences inspected): https://github.com/google/fonts/tree/main/ofl
- W3C, WCAG 2.2: https://www.w3.org/TR/WCAG22/
