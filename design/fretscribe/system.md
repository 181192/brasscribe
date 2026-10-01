# Fretscribe design system

Fretscribe follows **Brasscribe's design system** ([`design/system.md`](../system.md)) wherever this file
doesn't say otherwise: navigation per platform, list rows, cards, sheets and dialogs, progress with
steps, errors with recovery, empty states, settings, the music stand, appearance, focus and motion.
Keeping one copy of those rules is deliberate; two copies would drift.

This file holds only what Fretscribe adds or changes. Brand and words: [`brand/brand.md`](brand/brand.md).
Tokens: [`tokens/tokens.json`](tokens/tokens.json). Flows: [`flows.md`](flows.md). Why:
[`differences.md`](differences.md).

## 1. Rules that change

| Brasscribe rule | Fretscribe |
|---|---|
| The score owns colour (uncertain, very uncertain, loop, cursor) | **The tab owns colour**, with five signals: doubtful, out of range, cursor, repeat, selection. One level of doubt with a threshold, not two (see §3) |
| Brass only for brand moments | Blue ink only for brand moments, links and the cursor |
| Touch targets 44 pt, 48 pt in the player | 44 pt; 48 pt for review and fix-a-note; **64 pt for the practice transport and music stand** |
| One decision per step: What is this? → notes → output | **Check the song comes before the notes.** Output choices shrink to Share or print |
| Keyboard shortcuts with remap and off switch | Same, plus **pedals by default** (§6) and **Lock the tab** |
| Mute my part | "Mute the guitar" and Sound: Recording · Tab · Both. The recording is the default sound |
| Talking score is a separate view | The tab itself is navigable by screen reader (§7); the text export is the separate view |

## 2. Layout

As Brasscribe (phone < 600, tablet 600–1023, desktop ≥ 1024), with one change: **the practice view
is landscape-first on phone.** In portrait it shows one system of two bars with the fixed cursor;
landscape shows two to three systems. Neither ever shows tab smaller than `tab.line-space-min-phone-mm`.

## 3. Tab view

- **Staves:** tab with rhythm under it by default. Layers from the View menu: notation above (linked,
  treble 8vb for guitar, bass clef 8vb for bass), chord names, chord boxes, techniques, fingers. With
  notation on, rhythm under the tab turns off.
- **Numbers:** Fretscribe Tab, at least 1.5 × body size, the string line cut behind each number,
  −4% tracking on two digits.
- **Header:** instrument, tuning low to high, capo, tempo, printed and announced once.
- **Doubtful pitch:** a "?" above the tab column at 1.4 line spaces, and the numeral in `uncertain` on
  `uncertain-tint`. Only notes below the threshold (default 0.4) show it; a **Show ? for** slider in
  View raises it. Tapping the "?" or the number opens Fix a note.
- **Several valid places:** no mark. Alternatives appear in Fix a note.
- **Out of range:** a boxed "!" above the column in ink, and the words in the accessible name ("lower
  than your lowest string"). The Check the song screen links here when it finds any.
- **Cursor, repeat, selection, focus:** as in the brand colour table. Washes never stack; high contrast
  has shapes only.
- **Provenance:** in edit mode only, a pinned note shows a small pin under the number, and a changed
  note a short underline. The reading view stays clean.
- **Rendering:** alphaTab on every platform, recoloured from the tokens, with Fretscribe Tab as the
  number font. Guitar Pro import and GP7 export come from the same library later.

## 4. Components that are new

| Component | Rule | Native |
|---|---|---|
| **Tuning chip** | Always visible on Record, Practice and each library row: "E♭ standard · capo 2". Tap opens Tuning and capo. It's a button whose accessible name reads the whole state. | `Button` / `AssistChip` / `Button` with `CornerRadius` md |
| **Tuning and capo sheet** | Tuning list, **Custom** per string (note and Hz), capo stepper 0–12. Changing capo asks once: **Keep the sound** (new frets) / **Keep the shapes** (new sound). | `.sheet` / `ModalBottomSheet` / `ContentDialog` |
| **Check the song** | One row per finding (tuning, reference pitch, capo, octave, key and tempo): what was heard in words, and **Change**. Rows with nothing unusual collapse into "Key G major · ♩ = 96 · 4/4". Primary **Show the tab**. Nothing is re-solved until it is pressed (3.2.2). | `Form` / `LazyColumn` of `ListItem`s / `SettingsCard`s |
| **Level meter** | Words beside the bar: Too quiet · Good · Too loud, and a "noisy room" note. Never colour alone. Updates at most 10 times a second and is not announced continuously. | `Gauge` / `LinearProgressIndicator` / `ProgressBar` |
| **Fix a note** | One screen for both Check the notes (Skip · Keep, go to next) and a tap on any fret number in Practice (Done). Pitch first, then place, then techniques. | Sheet over the tab, the note scrolled into view above it |
| **Fretboard strip** (Fix a note) | A horizontal neck showing every place the selected pitch can be played: dot plus string name and fret. The chosen place is filled. Turned round for left-handed players. Each place is a 48 pt button; swipe on the number does the same (2.5.7). | Custom view with one accessibility element per place |
| **Pitch stepper** | **One lower / One higher** plus the candidates as buttons, each playing the note, then the recording at that spot. | Two `Button`s + a row of tonal buttons |
| **Play this in…** | For a selected phrase: Open position · Around fret [N] · On these strings · Easier / As played. Shows the result before **Use this**. | Sheet with radio rows and a stepper |
| **Practice player** | Order: Play (primary, 64 pt), Back to repeat start, previous/next bar, "Bar 13, beat 2", Speed, Repeat bars, Count-in, Metronome, Sound. Chrome hides after 3 s of playback and comes back on any tap, pedal or key; the back button and Lock the tab never hide. Lock the tab sits in the top bar. | As Brasscribe's player bar, with 64 pt transport |
| **Speed** | Steps of 5%, fine steps of 1% in its menu, pitch kept. **Speed trainer**: from, to, step and repeats per step, and it announces each change. | `Stepper` + `Menu` / two `IconButton`s + `DropdownMenu` / `NumberBox` |
| **Repeats list** | Saved repeats and section markers, each renameable, one tap to start. | `List` / `LazyColumn` / `ListView` |
| **Visual metronome** | A small dot moving between beat marks under the player, never a flash; haptic beat optional. Off with Reduce Motion unless turned on. | Custom |
| **Lock the tab** | A toggle in the player. While on, touches on the tab do nothing and the tab says "Locked" at the top; pedals, keys and the player still work. | `Toggle` / `IconToggleButton` / `ToggleButton` |
| **Provenance** | Per bar: **Back to Fretscribe's version**. Writing the song down again never overwrites notes changed by the player; a line says how many were kept. | Menu item + confirming dialog |

## 5. Your instrument

A settings group and the first-run screen: Instrument, Strings, Usual tuning, Which hand frets?, You
read. Each is a native picker row with its current value. Reference pitch (A = 440) sits under
**Advanced**. Changing the instrument never changes songs already written; each song keeps its own.

## 6. Pedals and keys

Works with any page-turner pedal or keyboard, no setup.

| Key | Default | Pedal (two-button) |
|---|---|---|
| Space | Play / pause | Right pedal |
| ← / PgUp | Back to repeat start, or previous bar when not repeating | Left pedal |
| → / PgDn | Next bar | — |
| Hold left / right pedal | Slower / faster by one step | Hold |
| L | Repeat these bars / Stop repeating | — |
| C | Count-in on/off | — |
| M | Metronome on/off | — |

Remappable in Settings › Pedals and keys, where single-key shortcuts can also be turned off (2.1.4). The
keys only act while the tab has focus.

## 7. Screen readers

- **Reading the tab:** one element per beat, bars as containers ("Bar 12 of 48, verse"). Beat labels at
  three levels, switchable from the rotor or actions menu:
  - Short: "7 on 3" · Standard: "Beat 2. 3rd string, fret 7, D♭, eighth." · Full: adds techniques and
    whether the note was checked or changed.
- Chords read as a shape name when one fits ("G, open shape"), with the strings on request.
- Repeated bars: "Same as bar 8". Tuning, capo and string numbering once per song; frets from the capo.
  Strings are always named by number (1st string is the highest), never by note name, which changes
  with the tuning and the instrument.
- **Rotor and actions:** Bars, Notes marked ?, Techniques, Play this beat, Play this bar.
- **Recording:** Fretscribe makes no announcements while recording; start and stop are confirmed by
  haptics and the large "Recording 0:42" label.
- **Playback:** **Announce between bars** holds speech for the gap after a bar.
- **Text exports:** Playing instructions (plain text) and Text tab, both from Share or print.

## 8. Share or print

As Brasscribe's, with these choices:
- **What:** The tab as shown (with its layers) · Chart (one page: chords, sections, riffs).
- **As:** PDF (default) · MusicXML · MIDI · Text tab · Playing instructions · Audio. Guitar Pro later.
- **Show ? marks**, on until every note is checked. Tuning and capo always print in the header. PDFs
  are tagged, and the tab figure's description points to the Playing instructions export.

## 9. Open questions

1. Is "?" above a tab column read as "check this note" by tab readers? Test next to Brasscribe's.
2. Hold-to-change-speed on a pedal: fast enough, or does it need its own pedal?
3. Portrait practice on phone: one system is enough to follow, or landscape only?
4. The hinted 16 px favicon leans towards a "document" icon; try a four-string version.
