# Readability review: Mikkel, solo cornet and brass band (golden output)

**Reviewed:** `data/golden/mikkel-arranged-band/brass-band.{pdf,musicxml}` as of 2026-09-25. This is the output **before** the free-time and duration fixes. Review again when those land.

**Method**
- Viewed the full-score PDF, 46 pages rendered at 90–110 dpi.
- Rendered the Solo Cornet part on its own through MuseScore to check the page turns. The part was extracted from the MusicXML, then `mscore -o solo.pdf solo.musicxml` produced 3 pages. `mscore -P` for all parts crashed before writing any output.
- Ran the heuristics in `qa/tools/musicxml_readability.py`.
- Bar numbers are MusicXML measure numbers. They match the printed numbers: bars 1–128, with no pickup bar.

**Viewpoint:** a player reading a part in a band rehearsal. Sight-reading, a stand partner, page turns, and a conductor calling "from letter B".

## Measured (heuristics)

Command: `uv run qa/tools/musicxml_readability.py data/golden/mikkel-arranged-band/brass-band.musicxml --bars`. Full output: [qa/reports/mikkel-golden-readability.md](../reports/mikkel-golden-readability.md). For the intro: `--range 1-4`, output in [qa/reports/mikkel-golden-readability-intro.md](../reports/mikkel-golden-readability-intro.md).

| Metric | Value |
|---|---|
| Parts / tacet | 18 / 1 (Soprano Cornet) |
| Pitched notes, playing parts | 5193 |
| Notes shorter than a 16th | 0.0% (no 32nds anywhere) |
| 16th notes, whole score | 10.0% |
| 16th notes, Solo Cornet | 40.2%; Euphonium 27.8%; Percussion 44.9% |
| 16th notes, bars 1–4 (the free-time intro) | Solo Cornet 30.8% (13 notes for about 31 s of music); Euphonium 37.5%; Bass Trombone 66.7% |
| Tuplets | 0% (the grid has 24 ticks per beat, but no triplets are written) |
| Tie stubs (a tie ending on a 16th) | whole score 1.2%; E♭/B♭ Bass 3.7%; bars 1–4, E♭/B♭ Bass 23.1% |
| Double- and triple-dotted values | Solo Cornet 9, Bass Trombone 7, E♭ Bass 6, B♭ Bass 6, Euphonium 5 |
| Rests per bar with notes | Euphonium 1.76 (highest); Solo Cornet 0.58 |
| Notes with 3 or more ledger lines | 2nd Horn 47.9%, 1st Horn 34.4%, 3rd Cornet 16.8%, 2nd Cornet 14.2%, Solo Horn 7.6% |
| Outside the heuristic extreme range | E♭ Bass 7 (written A5/A♭5, bars 4, 5, 122, 124, 126) |
| Printed accidentals, Solo Cornet | 37.5% of notes; bars with 6–10 accidentals: 19–25, 47–53, 109–116 |
| Awkward spellings | Solo Cornet E♯ (101, 108), F𝄪3 (127); E♯ also in Repiano (46, 108), Solo/1st/2nd Horn (50, 113), 1st Trombone (18, 46) |
| Uncertain notes (red) | Solo Cornet 31.6% (230 notes), all colour-only (WCAG 1.4.1) |
| Dynamics / rehearsal marks / text directions | 0 / 0 / 0 |
| Empty-bar ratio, playing parts | 20.9% |

## Issues a brass-band player would hit

Most severe first. Each item has bar numbers and an owner area (engine, arranger, writer, app renderer).

### 1. The intro is squeezed onto a fixed grid (bars 1–5): engine, free time

- The recording's opening is free time. The beat tracker's gaps there are 5.98, 1.38, 2.52, 2.08, 1.04, 1.28, 1.06, 3.52, 1.70 and 6.26 s (`composition.json` `beat_times`). Those roughly 31 s are notated as **bars 1–4 at ♩ = 136**. At 136 bpm that span would be about 18 bars. So in bar 2, one notated beat lasts 1–6 s of real time.
- The result: the sustained phrases of the opening appear as scattered 8ths and 16ths with rests.
  - Solo Cornet bar 2 has 4 rests: quarter, 16th, quarter, 16th.
  - Bar 5 opens with a **triple-dotted half rest**, then a 16th tied into bar 6.
- A player cannot perform this as written. Players need *ad lib.*, long notes, fermatas, and "a tempo" at bar 5.
- No tempo or expression text marks the free time. The only direction in the score is ♩ = 136 at bar 1.

### 2. Accompaniment entering in the solo intro (bars 2–4): arranger/engine, check by ear

- Flugelhorn, Solo/1st/2nd Horn and 1st/2nd Baritone enter at **bar 2 beat 3**, about 10 s into the recording, with quarter-note pads.
- The Euphonium enters with 16th figures (bars 2–3), and E♭/B♭ Bass sustain from bar 2 beat 2.
- `docs/songs/mikkel.md` says the intro is the solo line alone. Check by ear whether this is the strings or residual bleed in the "orchestra" stem. If it's bleed, the band parts should rest until bar 5.

### 3. Displaced bar lines after missed and extra beats (bars 5–6, 14, 56, 65, 70–72): engine, bar-line robustness

- **Missed beats:** the beat track has 0.84–0.86 s gaps (two beats) at bar 5 beats 1 and 4, bar 6 beat 3, and bar 14 beat 2. After each one, the notated meter drifts by one beat against the music.
- **Inserted beats:** 0.08–0.12 s gaps at bar 56 beat 4, bar 65 beat 2, and bar 70 beat 3 to bar 72 beat 3 (five spurious beats). They show up as tie chains and odd values:
  - Solo Cornet 64–65: dotted quarter tied to a **double-dotted half**.
  - Solo Cornet 71–73: half tied to quarter tied to 16th tied to dotted 8th.
- This is engine backlog §8 item 3. Until it's fixed, the app should show "meter uncertain" for these bars.

### 4. Rhythm spelling hides the beat (whole score): MusicXML writer

- Double-dotted notes and rests that cross beat 3 of a 4/4 bar, e.g. E♭ Bass bar 2 (double-dotted quarter from beat 2), bar 3, bar 30.
  - Brass-band parts should show the middle of the bar: half + tie, or quarter + dotted quarter.
  - Found in Solo Cornet 1, 5 (triple-dotted), 36, 38, 59, 65, 66, 74, 99; Bass Trombone 15, 30, 38, 46, 80, 123, 124; Euphonium 30, 31, 90, 96, 127.
- **Tie stubs** into 16ths are common in the basses: E♭/B♭ Bass bars 2, 3, 4, 13, 17, 28, 31, 42, 56, 57, 59, 63, 64, 70, 73, 117, 119, 122; Bass Trombone 4, 42, 56, 57, 117, 119, 122.
  - Each note is a long note plus a 16th, which reads like syncopation that isn't there.
  - This mostly comes from onset jitter on the grid. The duration fix should snap it.
- **Rest fragmentation:** Euphonium 56, 107 and 113 alternate 8th rests and notes (4 rests in a bar). Bass Trombone 15 has a quarter rest + 16th rest + … + double-dotted quarter rest.

### 5. Cornets and horns parked on the bottom note (many bars): arranger voicing

- 2nd and 3rd Cornet sit on **written F♯3** (3 ledger lines, the lowest valve note) in bars 51–53, 81–87, 90–96 and 112–114, and 3rd Cornet also in 108, 111 and 119.
- 1st and 2nd Horn reach written F♯3 in 66 and 82 of the 128 bars. That is 34% and 48% of their notes.
- F♯3 is a weak, hard-to-tune note on cornet and tenor horn. Hitting it this often suggests the voicer clamps to the range floor instead of choosing the next chord tone up.
- Horn players rarely read 3 ledger lines below the staff. The inner parts should sit around written C4–C5.

### 6. Bass line in the wrong octave (bars 4–5, 122–127): arranger octave placement

- E♭ Bass jumps from written D4 to **A5** (bar 4, a 19-semitone leap) and holds A5 through bar 5. That's concert C4: the top of the E♭ bass range, and not a bass line.
- The same happens at bars 122, 124 and 126 (written G♯5/A♭5), with a **30-semitone leap** in bar 126 (G♯5 to D3), then 4 ledger lines in 126–127.
- Bass Trombone reads A1, 3 ledger lines below the bass staff, through bars 20–28.
- Leaps larger than an octave: E♭ Bass 17, B♭ Bass 13, Bass Trombone 13.

### 7. Accidentals and spelling in the solo line (bars 19–25, 47–53, 109–116, 127): key estimate and spelling

- 37.5% of Solo Cornet notes carry an accidental. The key signature is written D major (concert C). Bars 19–25, 47–53 and 109–116 alternate D♯/D♮ and C♯/C♮ with 6–10 accidentals a bar, so the key signature doesn't fit these passages.
- This supports the open question in `docs/songs/mikkel.md` (C major or F lydian), or a local key change the key estimator misses.
- Spelling details:
  - bar 2: B♭4 next to C♯5 (mixed flats and sharps; also bars 11, 54, 105, 116)
  - bars 101 and 108: E♯5 (check whether F♮ is meant)
  - bar 127: **F𝄪3** where G3 is meant. No cornet player wants to read a double sharp on the lowest notes.

### 8. Uncertain notes shown only in red (Solo Cornet, 230 notes): writer and renderer

- In black-and-white print or photocopies, which is how band parts are usually shared, the uncertainty disappears.
- Uncertain notes cluster in the fast runs, e.g. bars 19–26, 40–55 and 105–116.
- Fix: shape encoding per `docs/accessibility/visual-design-tokens.md` §2.

### 9. Score and part layout: renderer/exporter

- **Only a full score is exported**: 46 pages, 2–4 bars per page, and page 1 holds only the title. Band players need **individual parts**.
- **Solo Cornet part** (3 pages, rendered locally):
  - The turn from page 1 to 2 falls at **bar 38/39**, in the middle of continuous playing (bars 34–58 have no rest longer than a bar).
  - The turn from page 2 to 3 falls in the rest at bars 82–88, which is fine but by luck.
  - Part layout should put turns in rests.
- **No multi-bar rests** in the part: bars 60–62, 82–88 and 97–98 print as separate whole-bar rests.
- **Soprano Cornet is tacet** for all 128 bars, yet takes a staff on every page. Hide empty staves in the score and export a "Tacet" part.
- **Staff labels repeat:** after page 2, the four cornets are all labelled "Cnt.", the three horns "Hn.", the baritones "Bar.", and the trombones "Tbn.". A reader can't tell which row is 2nd or 3rd Cornet. Use "Solo Cnt.", "Rep.", "2nd Cnt.", "3rd Cnt.", "Solo Hn.", "1st Hn." and so on. Percussion is labelled "Dr." after the first page.
- **No rehearsal marks and no dynamics.** A conductor has nothing to call ("from B"). Add rehearsal letters at phrase starts (every 8–16 bars) and at least the dynamics implied by the loudness curve (engine backlog §8 item 8).
- **Percussion**: the hi-hat is written out as 16ths in every bar (e.g. bars 33, 106–107), 45% of its notes. Slash or repeat-bar notation after the first bar of a groove would be much easier to read.

### 10. Ending (bar 128): arranger

- The solo ends with a half tied to an 8th, a dotted-8th rest and an isolated 16th.
- The basses end on written G♯4/C♯4 (concert B), which doesn't cadence in the notated key.
- There's no final fermata or closing chord. A reader can't tell the piece has ended rather than broken off.

## Checks for the re-review after the free-time and duration fixes

1. Bars 1–4 (or however many the intro becomes):
   - *ad lib.* text, long notes and fermatas, "a tempo" at the grid entry
   - `--range` on the intro shows 16th share < 10% and no triple or double dots
2. Tie stubs < 1% in every part; no double-dotted values across beat 3.
3. Solo Cornet bars 64–73 without tie chains.
4. Rerun `musicxml_readability.py --check`. The remaining violations should be only the ones that need arranger work (items 5–7) or renderer work (item 9).
5. Page turns in the Solo Cornet part fall in rests.

## Open questions

- The instrument ranges in `musicxml_readability.py` (`RANGES`) are heuristic defaults for a British-style band. They need confirming by a player, especially the E♭/B♭ Bass upper limit (written G5 here) and a comfortable bottom of written A3 for cornet and horn.
- The thresholds in `THRESHOLDS` (e.g. 16th share 35%, ledger-3 share 5%) are starting points. They should be tuned on published brass-band parts of similar difficulty.
