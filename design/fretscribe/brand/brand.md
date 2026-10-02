# Fretscribe brand

**Ruled Paper**: Fretscribe is a careful notebook. The lines are strings; it writes in ink what it heard
and in pencil what it isn't sure of. The reasoning and the alternatives considered are in
[`docs/fretscribe/research/04-brand-directions.md`](../../../docs/fretscribe/research/04-brand-directions.md).

## Family

Fretscribe and Brasscribe are siblings, not twins. A player who knows one should feel at home in the
other; nobody should mistake one for the other.

| | Shared | Brasscribe | Fretscribe |
|---|---|---|---|
| Ground | Paper and ink, one ink primary button, 12 px corners | Warm paper, warm ink | Cooler paper, blue-black ink; cool greys in dark |
| Brand colour | Used sparingly: mark, progress, onboarding | Brass | Blue ink `#1F5FAD` / `#8AB8F2` |
| Display face | Only for titles 28 px and up and the wordmark | Instrument Serif | Atkinson Hyperlegible Next 600 |
| Numbers in the score | — | Music font | **Fretscribe Tab** (below) |
| Mark | Drawn from the notation itself | A flat sign that opens like a bell | Six strings of graded gauge, cut by a slanted gap |
| Doubt | "?" means "check this note" | "?" / boxed "?" above the note | "?" above the tab column |
| Voice | Calm, specific, on your side; no "AI", no "we" | A good section leader | A good teacher |

## Name

- **Fretscribe**, one word, capital F, in all running text. The wordmark is set lower case; that is a
  logo, not a spelling.
- The apps are **Fretscribe** (the player app) and, where the products appear together, the shared
  **Bandroom** that runs the engine on a computer. Inside the app, say "Fretscribe": "Fretscribe isn't
  sure about these notes".
- The name is not translated or inflected in Norwegian ("tabben fra Fretscribe", not "Fretscribes tab").

## Mark

Six horizontal strings on a rounded tile, thin at the top (the high string, as in tab) and thick at the
bottom. A slanted gap cuts through all six, rising to the right. It reads as a downstroke across the
strings, as a pen stroke, and as the place a fret number interrupts its line.

| File | Use |
|---|---|
| `logo-mark.svg`, `logo-mark-dark.svg` | The mark on light and dark grounds, 24 px and up |
| `favicon-16.svg` | Pixel-hinted version for 16 and 32 px |
| `app-icon-fullbleed.svg` | iOS, store listings. Square, no baked corners; the art at 78% |
| `../dist/icons/android/res` | Android launcher icon, written by `build.py`: adaptive foreground with the art at 64% (the 78% art breaks the 66 dp safe zone), a monochrome layer and legacy squares |
| `wordmark.svg`, `wordmark-dark.svg` | "fretscribe" outlined, Atkinson Hyperlegible Next 600, −8/1000 em |
| `lockup.svg`, `lockup-dark.svg` | Mark plus wordmark |

Construction (48-unit grid): tile 48 with radius 11; strings from x 9 to 39, centres at y 9, 15, 21, 27,
33 and 39, heights 1.6 to 3.6 top to bottom; gap 5.5 wide centred at (24, 24), slope 0.55 horizontal
per unit of rise.

**Rules**
- Clear space: a quarter of the mark's height on every side. Minimum: the mark at 24 px (the hinted
  favicon below that), the wordmark at a 12 px cap height.
- Colour: ink, paper or blue ink only. No gradients, outlines, shadows or rotation.
- The mark never appears inside the tab, and never stands in for an action icon.

## Colour

Tokens: [`../tokens/tokens.json`](../tokens/tokens.json). Contrast report:
[`../tokens/contrast.md`](../tokens/contrast.md) (0 failures in light, dark, high contrast and high
contrast light).

**The tab owns colour.** Five signals appear in the tab and nowhere else, and each has its own shape,
so no signal depends on its hue:

| Signal | Shape | Colour (light / dark) |
|---|---|---|
| Doubtful pitch | "?" above the tab column; the numeral in the same colour on a faint wash | umber `#9A5200` / `#F2B24C`, wash `#FCF0DB` / `#3B3325` |
| No valid place (out of range) | Boxed "!" above the column, in **ink**, and the words in its label | ink (never red: red and umber can look alike with colour-blindness) |
| Playback cursor | 3 px vertical line, current beat column washed | blue ink `#1F5FAD` / `#8AB8F2` |
| Repeat | Band behind the bars, 3 px brackets at both ends, label "Repeat 12–16" | green `#1D6B55` / `#5FC4A3`, band `#E4F0EA` / `#18291F` |
| Selection | 1.5 px box, neutral wash | ink on `#E7E6E0` / `#2C3036` |

The focus ring is ink (paper on dark), 2 px with a 2 px gap, never a signal hue. Washes never stack: a
doubtful note inside a repeat keeps its own wash, and the repeat band stops behind it. High contrast
has no washes at all, only the shapes.

Blue ink appears outside the tab only as the brand: links, the progress bar, onboarding and empty
states. Buttons are ink (one primary per screen) or neutral.

**Doubt looks different from tab's own marks.** Parentheses around a fret number mean a ghost note (or
a tie across a line break), and circled numbers are an old half-note style and classical string
numbers. So the doubt mark is never a bracket, circle or outline around the numeral, and uncertainty is
never exported as parentheses. In MusicXML it travels as a note colour plus the confidence value in a
processing instruction on the note (an `<other-notation>` element makes MuseScore's importer hang).

## Type

- **Fretscribe Tab** (`fonts/FretscribeTab-Regular.ttf`): fret numbers only. It is Atkinson
  Hyperlegible Mono at a fixed weight of 600 with the plain zero as the default glyph. The original
  needs the `zero` OpenType feature for a plain 0, and alphaTab, canvas renderers and PDF export may not
  apply features, so the plain zero is built in. 1 has a flag and a foot; 6 and 9 have open tails; 0 and
  8 stay apart under blur. Built by `fonts/build_tab_font.py` (`uv run build_tab_font.py AtkinsonHyperlegibleMono[wght].ttf FretscribeTab-Regular.ttf`); OFL 1.1 (`fonts/OFL-FretscribeTab.txt`), renamed as a modified version.
  Still to confirm: alphaTab takes a custom font for tab numbers on every platform.
- **Atkinson Hyperlegible Next** 600 (`fonts/AtkinsonHyperlegibleNext-wght.ttf`, `fonts/OFL-AtkinsonHyperlegibleNext.txt`): the wordmark, onboarding and screen titles of 28 px and up.
- **Everything else: the platform's UI face** (SF Pro, Roboto, Segoe UI Variable, system-ui), which
  follows the system text size.
- **Notation:** Bravura or Leland (SMuFL, OFL).
- All fonts are bundled. Nothing loads from a font CDN: that would be a network request from a product
  that promises nothing goes online.

## Voice

Fretscribe talks like **a good teacher**: explains once, never gushes, admits doubt. The Brasscribe
voice rules hold word for word (say what happens in the player's words; one idea per sentence; verbs
on buttons; honest about uncertainty; every error says what to do next; shape and text, never colour
alone; no jargon; English and Norwegian both first-class; never "we").

| Moment | Copy |
|---|---|
| First run | Tab from any recording. Made on this phone. Nothing goes online. Free, with nothing locked. |
| Doubtful note | Fretscribe isn't sure about this one. It could be a D or a C♯. Listen to the bar and choose. |
| Another place | Also on the 2nd string, fret 3. Choose the one that suits your hand. |
| Out of range | This note is lower than your lowest string. Is the tuning right? [Change tuning] |
| Empty library | Nothing written down yet. Record a riff or open a recording. |
| Error | This file can't be opened. It looks like a video with no sound. Try an MP3, WAV or M4A file. [Choose another file] [Record instead] |

### Words

| Concept | English | Norsk (bokmål) | Avoid |
|---|---|---|---|
| The finished notation | tab · tab and notation | tab · tab og noter | transcription, sheet |
| Make it from audio | write down the notes | skrive ned tonene | transcribe, AI, generate |
| Before the tab | Check the song | Sjekk sangen | analysis, detection |
| The doubtful notes | notes marked ? | toner merket ? | low confidence, the orange notes |
| Where on the neck | string · fret · position | streng · bånd · posisjon | |
| Move a note to another string | Play it somewhere else | Spill den et annet sted | re-finger, reassign |
| A phrase in one place | Play this around fret 7 | Spill dette rundt bånd 7 | position lock |
| Capo change | Changing the capo changes the frets. The notes stay the same. (Once the shapes can be kept instead: Keep the sound / Keep the shapes) | Endrer du capo, endres båndene. Tonene er de samme. (Senere: Behold klangen / Behold grepene) | transpose (alone) |
| Note names in Norwegian | B (the note) | H; «Drop H», «HEAD», «D G H E». B is B flat, and E flat is Ess | B for the note H |
| Repeat a passage | Repeat bars 12 to 16 · Stop repeating | Gjenta takt 12 til 16 · Slutt å gjenta | Loop, A–B |
| Hands-free | Pedals and keys | Pedaler og taster | HID, MIDI (in Settings detail only) |
| Stop touches on the tab | Lock the tab | Lås tabben | Lock screen |
| Hand | Which hand is on the neck? · Left hand on the neck (most players) · Right hand on the neck (left-handed instrument) | Hvilken hånd er på halsen? · Venstre hånd på halsen (de fleste) · Høyre hånd på halsen (venstrehendt instrument) | lefty mode, "frets" as a verb |
| Output | Share or print | Del eller skriv ut | Export (desktop menu bar only) |
| Your computer | Fretscribe on your computer (installer and app lists: Bandroom) | Fretscribe på datamaskinen | engine, server |
