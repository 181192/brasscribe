# target-fretted

Tablature fingering for fretted instruments. It chooses a string and a fret for each note of a
passage, so the passage can be written as tab for guitar, bass, ukulele or mandolin, and writes the
result as tablature in MusicXML, as a plain-text tab, and as playing instructions in words.

The input is the shared symbolic model's notes from `brasscribe-core` (`Note`: concert MIDI
`pitch`, and `start` and `dur` in ticks at `TICKS_PER_BEAT`). The output gives each note a string
and a fret, plus the other places it could be played. Pitches are never changed. When no string can
sound a note, the note is flagged `out_of_range` and keeps its pitch.

```rust
use target_fretted::{assign, check, preset, Options, Style};

let guitar = preset("guitar-standard").unwrap().with_capo(2);
let opts = Options { style: Style::OpenPosition, ..Options::default() };
let fingering = assign(&guitar, &notes, &opts)?;
assert!(check(&guitar, &notes, &fingering, &opts).is_empty());
```

## Instruments as data

An `Instrument` is a `Tuning` (one `StringSpec` per string, string 1 first), a fret count, a scale
length in millimetres, a capo and the clef it is written in (`notation`).

- **Strings are numbered from 1**, the highest line in tab. The solver never infers pitch order from
  the string number. It reads each string's `open_pitch`, so re-entrant tunings work: on a high-G
  ukulele, string 4 (G4) is higher than string 3 (C4).
- **Mandolin** has one string per course.
- **Short strings.** `first_fret` models a string that starts partway up the neck, such as a banjo's
  5th string (`first_fret: 5`). Frets 1 to `first_fret` do not exist on that string. Its frets are
  numbered as on the full neck, so the first one is written 6.
- **Capo.** The capo raises every full-length string. Output frets are relative to the capo, with 0
  meaning the capo'd open string. A short string that starts at or above the capo is not covered by
  it.

Presets (`PRESET_IDS`, `preset(id)`):

| Id | Tuning (string 1 first) | Frets | Scale |
|---|---|---|---|
| `guitar-standard` | E4 B3 G3 D3 A2 E2 | 22 | 648 mm |
| `guitar-eb-standard` | E♭4 B♭3 G♭3 D♭3 A♭2 E♭2 | 22 | 648 mm |
| `guitar-d-standard` | D4 A3 F3 C3 G2 D2 | 22 | 648 mm |
| `guitar-c-standard` | C4 G3 E♭3 B♭2 F2 C2 | 22 | 648 mm |
| `guitar-drop-d` | E4 B3 G3 D3 A2 D2 | 22 | 648 mm |
| `guitar-drop-c` | D4 A3 F3 C3 G2 C2 | 22 | 648 mm |
| `guitar-drop-b` | C♯4 G♯3 E3 B2 F♯2 B1 | 22 | 648 mm |
| `guitar-dadgad` | D4 A3 G3 D3 A2 D2 | 22 | 648 mm |
| `guitar-open-g` | D4 B3 G3 D3 G2 D2 | 22 | 648 mm |
| `guitar-open-d` | D4 A3 F♯3 D3 A2 D2 | 22 | 648 mm |
| `guitar-open-e` | E4 B3 G♯3 E3 B2 E2 | 22 | 648 mm |
| `guitar-7-standard` | E4 B3 G3 D3 A2 E2 B1 | 24 | 648 mm |
| `guitar-7-eb-standard` | E♭4 B♭3 G♭3 D♭3 A♭2 E♭2 B♭1 | 24 | 648 mm |
| `guitar-8-standard` | E4 B3 G3 D3 A2 E2 B1 F♯1 | 24 | 686 mm |
| `bass-4-standard` | G2 D2 A1 E1 | 21 | 864 mm |
| `bass-4-eb-standard` | G♭2 D♭2 A♭1 E♭1 | 21 | 864 mm |
| `bass-4-d-standard` | F2 C2 G1 D1 | 21 | 864 mm |
| `bass-4-drop-d` | G2 D2 A1 D1 | 21 | 864 mm |
| `bass-4-bead` | D2 A1 E1 B0 | 21 | 864 mm |
| `bass-5-standard` | G2 D2 A1 E1 B0 | 24 | 864 mm |
| `bass-5-drop-a` | G2 D2 A1 E1 A0 | 24 | 864 mm |
| `bass-6-standard` | C3 G2 D2 A1 E1 B0 | 24 | 864 mm |
| `ukulele-high-g` | A4 E4 C4 G4 (concert) | 18 | 380 mm |
| `ukulele-low-g` | A4 E4 C4 G3 (concert) | 18 | 380 mm |
| `ukulele-baritone` | E4 B3 G3 D3 | 19 | 483 mm |
| `mandolin` | E5 A4 D4 G3 | 20 | 350 mm |

`ukulele(UkuleleSize::Soprano | Concert | Tenor, low_g)` builds the other ukulele sizes: 330, 380
and 432 mm. A custom tuning is just another `Tuning`.

A 5-string bass already reaches D1 on its low B string, so its drop tuning lowers that string to
A0 instead of adding a drop D.

### Families and tuning suggestion

Presets group into **families**: the same instrument in different tunings (`preset_family(id)`,
`family_presets(family)`). The families are `guitar`, `guitar-7`, `guitar-8`, `bass-4`, `bass-5`,
`bass-6`, `ukulele`, `ukulele-baritone` and `mandolin`. The first preset of each family is its
standard tuning.

`suggest_tunings(family, notes, capo)` ranks every preset of a family by how well it fits the notes.
It sorts on these keys, in order:

1. fewest out-of-range notes;
2. the lowest note is exactly the tuning's lowest open string, the same MIDI pitch
   (`low_string_fits`);
3. closest to the standard tuning, as semitones summed over the open strings;
4. most notes an open string can play (`open_notes`), then fewest notes that can only be played
   above the 12th fret, then preset order.

Standard tuning wins unless the notes give evidence against it:

- An E♭ riff that sits on E♭2 ranks E♭ standard first, although drop D is closer to standard and
  also reaches its notes.
- A bass line down to D1 ranks `bass-4-drop-d` first.
- A melody whose lowest note is C4 or D3 stays in standard. The JSON response carries this ranking for a preset instrument, so the song check
can offer "Sounds like drop D" and the player confirms it.

## How notes are placed

Notes that start on the same tick form an **event**. Notes of the same pitch in one event (a
doubling from two voices) sound as one note and share a position. The exception is a strummed
ukulele or mandolin chord that is an open shape from the shape table (below): there each doubled
note gets its own string, as in the shape.

For each event, the solver lists **voicings**: each note on its own string, at a position that
sounds its pitch within the neck, above the capo and not on a short string's missing frets. It
tries three things in order and uses the first that gives any voicings:

1. voicings with every note placed and a hand span within the limit;
2. voicings with every note placed, whatever the span;
3. voicings that place as many notes as possible. This happens when more notes start together
   than there are strings.
   - The span limit stays on here: the solver leaves a note without a string rather than stretch
     past the limit.
   - It only drops the limit when no note at all can be placed within it.

**Limits on very large clusters.** The search stops after 50,000 complete voicings per step
(`LEAF_CAP`). It tries strings in order, string 1 first. So on a very large cluster, the voicings
it finds favour the low-numbered (high-sounding) strings, and a cheaper voicing that leans on the
other strings may never be seen. Ordinary chords come nowhere near the cap. Of the voicings found,
the 64 cheapest are kept.

Each voicing is paired with a **hand position**, the neck fret under the index finger. The position
may sit up to three frets below the lowest fretted note, as long as the reach to the highest fretted
note stays within the hand limit. An all-open voicing leaves the hand free, so it can pair with any
position.

A Viterbi search then picks the cheapest path through these states. Ties go to the first state in
enumeration order, so the same input always gives the same output.

### Cost model

Distances are millimetres along the neck. Fret *f* is `L * (1 - 2^(-f/12))` from the nut, where
*L* is the scale length. Spans measured this way come out wider in frets on a ukulele or mandolin
and narrower on a bass, with no per-instrument fret rules.

Per state:

- **Span.** A small cost per mm between the lowest and highest fretted note. Open strings are
  free.
- **Reach.** A quadratic penalty once the reach from the index finger passes the comfortable span
  (`HandLimits::comfortable_mm`, 100 mm by default). A voicing wider than `HandLimits::max_mm`
  (140 mm) is only used when nothing narrower exists.
- **Height.** A cost per mm the hand sits above the nut (or the capo).
- **Open strings.** A bonus or penalty per open string, set separately for chords and for
  single-note lines.
- **Chord shapes.** A bonus for a voicing from the shape table (below).

Per transition from one event to the next:

- **Shift.** A fixed cost per hand move plus a cost per mm moved. Both are scaled by
  `1 + 0.25 s / Δt`, so a shift with no time to make it costs more. Ticks become seconds through
  `Options::tempo_bpm`. Without a tempo, time is counted in beats, as at 120 BPM.
- **Dropping below the hand.** In a single-note line, a note more than a hand's width (three frets)
  below the neighbouring hand position costs extra, per mm of the drop. This is the
  "twelfth-fret solo written as open strings" failure: a line played up the neck should not dip to
  an open string or a first-position fret on a thin string for one note.
- **Techniques.** Breaking a technique constraint (below) costs so much that the search only does it
  when nothing else fits.

Style presets (`Style`) re-weight these terms:

| Style | Height | Open strings | Shifts | Chord shapes |
|---|---|---|---|---|
| `OpenPosition` | strongest pull to the nut | bonus in chords and lines | cheapest | power chords and open shapes, strongest |
| `AsPlayed` (default) | mild | small bonus in chords, neutral in lines | a fixed cost per move keeps a lick in its box | power chords and open shapes |
| `Lead` | almost none | penalty in single-note lines | also twice the cost per mm, and excursions are not set aside, so a phrase stays in one position | power chords only |

The weights are in one table in `src/solve.rs`.

**Excursions.** One or two stray notes far above or below a line, or a short fill, should be
reached and left. They should not drag the notes around them along the neck. In `OpenPosition` and
`AsPlayed` the solver therefore sets excursions aside, places the rest of the line as if they were
not there, and then places each excursion between its neighbours, which stay where they are. An
excursion is a run of single notes that the line leaps to and straight back from:

- one or two notes, each an octave or more from the notes on both sides of the run and on the same
  side of both; or up to 8 notes, each more than an octave from them;
- the notes on the two sides are within 5 semitones of each other, so the line carries on where it
  was;
- one or two stray notes can also open or close the passage. With the line on one side only, its
  next three notes must stay within 5 semitones of the nearest one;
- it stands alone: at least three notes of the line lie between it and the next excursion;
- no note of the run, and neither neighbour, is tied to another by a technique.

What is not an excursion pays the ordinary shift costs, so a chord shape or a box holds:

- the top of an arpeggio, a fifth or a seventh above a root, a run that climbs and stays, and a
  line that moves by step;
- a figure that alternates between two registers, such as broken octaves or a pedal point under a
  melody. It has no line to return to.

`Lead` sets nothing aside. It keeps a phrase with wide leaps in one position.

Known limit: two excursions with fewer than three notes of the line between them are both left in
the line and get the ordinary costs, so the notes around them can still be pulled towards them.

**Repeats.** When a run of four events has the same pitches as an earlier run, a second pass gives
the occurrences one fingering. A strong cost for deviating does this, so a pin or an impossible
reuse still wins.

- In `Lead`, every occurrence takes the first occurrence's fingering.
- In `OpenPosition` and `AsPlayed`, the occurrences of a passage vote, each with its whole
  fingering. The fingering most of them got on their own wins. On a tie the cheapest wins, then the
  earliest. So one bar in an odd context, such as the first bar after a passage up the neck,
  follows the other bars and does not pass its fingering on to them. A bar is never pieced together
  from two fingerings, so a pitch repeated in it keeps its place.
- Excursions are left out before repeats are looked for, so a bar with a stray note in it still
  counts as a repeat of the bar without.

**Pins.** `Options::pins` fixes the string of a note. The solver treats a pin as a hard constraint,
and the neighbours and the rest of a chord reflow around it. A pin on a string that cannot sound the
pitch is ignored by the solver and reported by the check.

### Chord shapes

`src/shapes.rs` holds two small tables:

- **Power chords.** Root and fifth, with or without the octave, on adjacent strings, root on the
  lowest. The tuning decides the frets: `x-3-5-5` for C5 in standard tuning, the one-finger `5-5-5`
  for G5 in drop D.
- **Open shapes for strummed ukulele and mandolin chords.** These fill every string, so they double
  a pitch on a second string. Ukulele G is `0-2-3-2`, Am `2-0-0-0`, F `2-0-1-0` and C `0-0-0-3`
  (high and low G). The mandolin has the common GDAE shapes. Doubling only happens when the input
  already holds the doubled note, as a transcribed strum does. The solver never adds notes.

A style turns a table off by setting its weight to zero.

### Techniques

A note carries a list of techniques, so one note can be both bent and let ring:

- in JSON, `techniques` on the note, for example `["bend", "let-ring"]`;
- in Rust, one list per note passed to `assign_with_techniques` and `check_with_techniques`.

Names are kebab-case: `slide`, `hammer-on`, `pull-off`, `bend`, `vibrato`, `let-ring`, `dead-note`.

- **Slide, hammer-on, pull-off and bend** keep the string of the note they come from. That is the
  note among those starting most recently before it that is closest in pitch.
  - A bend must also be fretted.
  - The string is kept only within a reach the hand can play legato: 12 frets for a slide, 5 for a
    hammer-on or pull-off. A jump beyond that is reported as `technique-reach`, not forced onto the
    string.
- **Let ring** reserves the note's string until the note's written end, so no later note may start
  on it while it sounds. The search sees only neighbouring events. For a later note further on, the
  string is taken away and the passage is solved again, up to eight times.
- **Vibrato** is accepted and does not constrain the position yet.
- **Dead note** (a muted, percussive note) does not constrain the position. It is written as an x.

A technique that cannot be honoured is left to the check to report.

**Alternatives.** Each note lists every other position that sounds its pitch. They are ranked by
the local cost of playing the note there: the cheapest state of that event using the alternative,
with its transitions to the chosen neighbours. There is no full re-solve per alternative.

## Playability check

`check` is independent of the solver. It returns hard violations only:

- two different notes starting together on one string (`shared-string`);
- a fretted span wider than `HandLimits::max_mm` among notes starting together (`span-too-wide`);
- a string or fret that does not exist (`fret-out-of-range`), or one that sounds another pitch
  (`wrong-pitch`);
- a pinned note that is not on its pinned string (`pin-not-honoured`);
- an in-range note left without a string, or an out-of-range flag that does not match the
  instrument (`no-string`);
- a slide, hammer-on, pull-off or bend on another string than the note it comes from
  (`technique-string`), or a bend on an open string (`bend-on-open-string`);
- a slide, hammer-on or pull-off farther from the note it comes from than its reach
  (`technique-reach`);
- a note that starts on a string a let-ring note still reserves (`ring-cut`). This check looks at
  notes that overlap in time, not only notes that start together.

## Tablature as MusicXML

`write_tab_musicxml(&TabScore, &TabOptions)` writes a solved passage as one MusicXML 4.0 partwise
document. It answers with a `TabDocument`: the text (`musicxml`) and how many notes it had to move
to a place that can be written (`adjusted_notes`, see Rhythm and measures). The same input always
gives the same text.

```rust
use target_fretted::{assign, preset, write_tab_musicxml, Layout, Options, TabOptions, TabScore};

let guitar = preset("guitar-standard").unwrap().with_capo(2);
let fingering = assign(&guitar, &notes, &Options::default())?;
let score = TabScore::new("Study", &guitar, &notes, &[], &fingering)?.with_tempo(88.0).with_meter(3, 4).with_key(2, "major");
let xml = write_tab_musicxml(&score, &TabOptions { layout: Layout::Tab, ..TabOptions::default() })?.musicxml;
```

A `TabScore` holds the title, the instrument, tempo, one time signature, one key, and each note with
its string, fret, confidence and techniques. `TabScore::new` builds it from the solver's input and
output and refuses input that does not fit together: a fingering for another number of notes or
other pitches, a string without a fret, and a string and fret that the instrument does not have or
that sound another pitch than the note's (`note 1: string 1 fret 0 sounds pitch 43, not the note's
33`). A fingering edited by hand is checked the same way; a note may be left without a place. `with_composition` takes tempo, first meter and
first key from a `Composition`.

The writer checks the score first (`TabScore::validate`), also one built by hand, and answers with
an error instead of changing what it was given:

- a time signature whose lower number is not 1, 2, 4, 8 or 16, or whose upper number is not 1 to 32;
- more than 7 sharps or flats, or a tempo outside 10 to 600;
- more than `MAX_NOTES` notes;
- a note without a length, outside the model's tick range, outside MIDI 0-127, with a confidence
  that is not a number, or with a string or fret the instrument does not have;
- a doubt threshold outside 0 to 1.

Control characters in the title, the instrument's name and the tuning's name are left out (a tab or
line break becomes a space), so the file stays well-formed.

### Layouts

| `layout` | Staves | Rhythm |
|---|---|---|
| `tab-and-notation` (default) | one part, two staves: notation (staff 1) above tab (staff 2), the same notes on both | on the notation staff; tab notes have `<stem>none</stem>` and no beams |
| `tab` | the tab staff | in the tab notes: types, dots, ties, rests, stems down and beams per beat, so a renderer can draw it under the staff |
| `notation` | the notation staff | on the staff; no string or fret |

### The tab staff

- `<clef>` `TAB`, and `<staff-details>` with `<staff-lines>` = the number of strings.
- One `<staff-tuning line="k">` per string. **Line 1 is the bottom line**, so line *k* is string
  *n + 1 - k*: the last string of the tuning comes first. On a high-G ukulele line 1 is G4, above
  the C4 on line 2.
- Each note has its sounding `<pitch>` and `<technical><string>` and `<fret>`. String 1 is the top
  line.
- Open strings are named with flats when the tuning's name has a flat sign, or when flats give the
  simpler names (C standard: E♭ and B♭); otherwise with sharps.

### Capo

Frets are relative to the capo: 0 is the capo'd open string. The pitch is always the sounding one,
and the header always says `Capo n`. `TabOptions::capo` chooses how the staff says it:

| `capo` | `<staff-tuning>` | `<capo>` |
|---|---|---|
| `tuning` (default) | the open strings as they sound with the capo on | none |
| `element` | the tuning without the capo | the capo fret |

`tuning` is the default because it is what readers keep. `element` follows the MusicXML definition
(the capo raises the strings given by `<staff-tuning>`, so pitch = tuning + capo + fret), but a
reader that ignores `<capo>` then sees frets that do not match the tuning.

Readers checked: **MuseScore 4.7 only.**

- With `tuning` it keeps every string and fret as written.
- With `element` it drops `<capo>`: it keeps the pitches, checks each string and fret against the
  tuning without the capo, and rewrites the ones that no longer match. The tab then shows frets
  counted from the nut, and some notes move to another string.

Guitar Pro, Dorico and alphaTab have not been checked. Check the round trip in the program the file
is for before choosing `element`.

### Notation staff

Pitches are written as they sound. An instrument written an octave above its sound gets a clef with
`<clef-octave-change>-1</clef-octave-change>`, and no `<transpose>`. The clef is the instrument's
`notation` field:

| `notation` | Clef | Presets |
|---|---|---|
| `treble-8vb` | treble, sounding an octave lower | guitars, baritone ukulele |
| `bass-8vb` | bass, sounding an octave lower | basses |
| `treble` | treble at pitch | ukuleles, mandolin |

A custom instrument may leave `notation` out. It then gets bass clef 8vb when its highest open
string is below E3, treble 8vb when its lowest is below C3, and plain treble otherwise
(`Instrument::notation_clef`). `TabOptions::clef` overrides the instrument for one document.

Pitches are spelled by the shared `spelling` module. `<accidental>` elements are not written; a
reader works them out from the pitch and the key.

### Rhythm and measures

- `<divisions>` is 24, the model's ticks per quarter note, so durations are ticks.
- **One rhythmic voice.** Notes that start together are a chord (`<chord/>`, low to high). A chord
  lasts until its longest note ends or the next note starts, whichever comes first. A bass note held
  under a melody is therefore cut at the next melody note.
- Two notes of one pitch on one position (a doubling from two voices) are written once, with the
  higher confidence and the note index of the first of them (see The note index).
- Values are split and tied to show the beat and the bar line, on notes and rests alike: by the
  shared `rhythm_spelling` module on quarter-note beats, and on dotted-quarter beats in 3/8, 6/8,
  9/8 and 12/8. Other meters in eighths (5/8, 7/8) are split on quarter notes. An empty bar is a
  whole-measure rest. Every other note and rest has a `<type>`.
- **The grid.** A start or an end that no note value can spell is moved to the nearest one that
  can, and `adjusted_notes` counts the notes this changed (0 for input already on the grid).
  - Each quarter-note beat is written either in 32nds (every 3 ticks) or in triplet 16ths (every 4
    ticks), whichever is nearer to the starts and ends inside it. A tie goes to the 32nds.
  - A note squeezed to nothing gets the shortest value of its beat. Two notes moved to one start
    become a chord.
  - A note cut short by its chord or by the next note does not count as moved.
- **Triplets.** A triplet beat is filled with triplet 16ths, eighths and quarters, each with
  `<time-modification>` 3:2, under one `<tuplet>` bracket that starts and stops inside the beat,
  on each staff. A triplet value that crosses the beat is tied at the beat.
- **Compound time has no tuplets.** In 3/8, 6/8, 9/8 and 12/8 everything is on the 32nd grid and
  written in plain and dotted values; a duplet is two dotted eighths.
- Beams join notes shorter than a quarter inside one beat: a quarter, or a dotted quarter in 3/8,
  6/8, 9/8 and 12/8.
- A pickup shorter than a bar is measure 0 with `implicit="yes"`. A longer one starts on a bar line
  with rests before it.
- The TAB clef names line 5 whatever the number of lines. MuseScore reads it and leaves the line out
  when it writes.
- The first measure holds the key, the time signature, a `<metronome>` with `<sound tempo>` (quarter
  notes per minute), and the header as words: the tuning's name, the open strings from the bottom
  line to the top, and the capo, for example `Drop D: D A D G B E, Capo 3`. The part name is the
  instrument's name.

### Techniques

Marks are written on the tab staff, or on the notation staff when it is the only one. In a pair of
staves the notation staff gets only the slurs and the x noteheads.

| Technique | Written as |
|---|---|
| hammer-on, pull-off | `<hammer-on>` / `<pull-off>` `type="start"` on the note it comes from and `type="stop"` on the note that has it, plus a `<slur>` between them |
| slide | `<slide type="start">` and `type="stop"` on the same two notes |
| bend | `<bend><bend-alter>` on the note the bend starts from, with the interval up to the bent note in semitones, and a `<slur>` to the bent note |
| vibrato | `<ornaments>` with a `<wavy-line>` start and stop |
| let ring | the words "let ring" where a run of ringing notes starts, and `<tied type="let-ring">` on each |
| dead note | `<notehead>x</notehead>` |

- A tied note carries the marks that end on it on its first piece and the marks that leave it on its
  last.
- A bend is only written when the note it comes from is 1 to 4 semitones lower.
- The bent note keeps the fret the solver gave it, which is the fret that sounds its pitch without
  bending. So the two numbers read "from 7, bent up to the pitch of 9", and every `<pitch>` agrees
  with its string and fret.

### The note index

Every `<note>` with a pitch says which note of the input it was written for, as a processing
instruction at the end of the `<note>`:

```xml
<note>
  ...
  <?fretted-note 17?>
</note>
```

- The number is the note's position in the input, counted from 0: `TabScore::notes`, which is the
  `notes` list of a JSON request and the order of its `fingering`.
- A drawn note can be matched to its note this way where the ticks cannot: when its start or
  length was moved to the grid, when it was cut by its chord or the next note, in a chord, and on
  a tied note.
- Every tied piece of a note carries the note's index.
- In a pair of staves the note carries it on both staves.
- A rest has none. That includes the rest that stands for a note without a place on the tab staff;
  the notation staff has that note, with its index.
- Notes written once (a doubling: one pitch on one position at one start) carry the index of the
  first of them in the input. The other indices of the doubling are not in the document.
- A doubtful note has the index first and the confidence after it.

### Doubt and range

- A note whose confidence is below `TabOptions::doubt_below` (default 0.4; 0 marks none) is
  **doubtful**:
  - `color` on the `<note>` and on its `<notehead>` (`#9A5200`);
  - one `?` as words above the column, before the chord's first note;
  - the confidence as a processing instruction, the last child of the `<note>`:

    ```xml
    <note color="#9A5200">
      ...
      <?fretted-note 7?>
      <?fretted-confidence 0.31?>
    </note>
    ```

    The value has two decimals, from 0.00 to 1.00. A tied note carries it on its first piece.
- Doubt is never a parenthesis or another notehead shape: those mean ghost notes, ties and half
  notes in tab. It never changes a pitch, string or fret.
- The confidence is not an `<other-notation>` element: MuseScore 4.7 stops responding when it reads
  one. A processing instruction is skipped by readers that do not know it.
- **A note without a place** (out of range, or more notes than strings) is never shown on the tab
  staff, because any fret there would be a wrong pitch:
  - the notation staff writes it as any other note;
  - the tab staff leaves it out of its chord, or writes a rest of the same length when the chord has
    no other note;
  - boxed words above the column name it: `! D1` (`enclosure="rectangle"`). In the notation-only
    layout the words stand above the note.
  - A slide, hammer-on, pull-off or bend to or from such a note is not written.
- In a pair of staves the `?` and `!` are on the tab staff.

### Round trip in MuseScore

Checked by converting generated files with MuseScore 4.7 (`mscore -o out.musicxml in.musicxml`, and
to PDF):

- kept: the number of tab lines, every `<staff-tuning>` (also the re-entrant ukulele and the 5-string
  bass), every string and fret with the default capo encoding, the two-staff part, the octave clef,
  ties, chords, triplets, slurs, slides, let-ring ties, x noteheads, the note colour, the rest that
  stands for an out-of-range note, the `?`, the boxed `!`, header and tempo, and notes that were
  moved to the grid in 9/8, 6/8 and 4/4;
- changed: a `<wavy-line>` is drawn as a trill line, and with `"capo": "element"` the frets are
  rewritten (see Capo);
- lost: `<hammer-on>`, `<pull-off>` and `<bend>` (the slurs stay), the confidence and the note
  index.

`cargo test -p target-fretted --test tab_musicxml -- --ignored musescore` repeats the check on the
study with the note index in it: MuseScore must write a file with every note, string and fret. It
starts MuseScore (`MSCORE`, `mscore` on the path, or the macOS application), so it only runs when
asked for, and says so when MuseScore is missing.

## Tablature as text

`write_tab_text(&TabScore, &TabOptions, &TextOptions)` writes the same score as a text tab for a
monospace font: a printed page, a message or a forum post. It reads the plan the MusicXML is written
from, so both hold the same notes, chords, bars and marks. The same input always gives the same
text.

```text
Made-up passage
Bass
Tuning: Standard (E A D G), bottom line to top
Capo: none
Tempo: 96 quarter notes per minute
Time: 4/4

     1                2
          ?
G|--|-------------0--|--------||
D|--|---------0h2----|--------||
A|--|-0---3----------|-----5/7||
E|-3|----------------|--------||

?  a note to check: it was not heard clearly
h  hammer-on
/  slide up
```

- **Header:** title, instrument, tuning (its name and the open strings from the bottom line to the
  top), capo, tempo and time signature. The capo line is always there: `Capo: none` without one.
- **Lines:** one per string, string 1 on top, named after its open string. A mandolin has one line
  per course. Sharps and flats are `#` and `b`, and the labels are filled to one width, so apart
  from the title and the names of the instrument and the tuning the text is ASCII and lines up in
  any monospace font.
- **Columns:** notes that start together stand in one column. Every column is as wide as the widest
  number of the score, so frets of two digits keep the columns in line.
- **Time:** inside a bar the columns are an even grid, as fine as the bar's notes need, so a
  quarter note takes twice the room of an eighth. A bar that would need more than 16 columns that
  way is drawn beat by beat, each beat as wide as its own notes need. A rest is empty line.
- **Ties:** a note held over a beat or a bar line is written once, where it starts; the line stays
  empty while it sounds. No number is ever repeated in parentheses.
- **Bars:** a bar line after every bar, two after the last, and the bar's number above its first
  column where there is room. A pickup has no number.
- **Width:** a line holds as many whole bars as fit in `TextOptions::width` characters (72 by
  default, 24 to 400). A bar is only divided when it alone is wider than the page; then it takes
  lines of its own. The header and the legend are not wrapped.
- **Techniques:** `h`, `p`, `/`, `\` and `b` stand before the note they lead to (`5h7`, `7p5`,
  `5/7`, `7\5`, `7b9`); `~` after a note with vibrato; `x` in place of the fret of a dead note;
  `let ring` above the first note that rings, shortened to `l.r.` or `r` where the next one leaves
  no room.
- **Doubt and range:** a `?` above the column of a doubtful note (`TabOptions::doubt_below`; 0
  writes none), never a parenthesis. A `!` above the column of a note without a place; the note is
  not on the lines, and the legend names it with its bar (`bar 2: F#1`). A second note given the
  same string in one chord is treated the same way: a line holds one number per column.
- **Legend:** one line per mark that occurs in the tab, and none when there are no marks.

`write_tab_text` refuses what `write_tab_musicxml` refuses, and a width outside 24 to 400.

Both text writers take time that grows with the length of the passage: at the cap of 20,000 notes
each is written in a fraction of a second.

## Playing instructions

`write_playing_instructions(&TabScore, &TabOptions, &TextOptions)` writes the score in words, for
someone who reads with a screen reader or a braille display: bar by bar and beat by beat, which
string and fret to play and for how long. `TextOptions::lang` is `en` or `nb` (a tag that starts
with `nb` or `no` is Norwegian Bokmål); any other language is refused.

```text
Bass, 4 strings.
String 1 is the string nearest the floor as you play. String 4 is nearest the ceiling.
Tuning: Standard. Open strings from string 4 to string 1: E, A, D, G.
Capo on fret 2. Frets are counted from the capo.
Tempo: 96 quarter notes per minute.
Time: 4 4 time.
A note marked "to check" was not heard clearly.

Bar 1
  Beat 1. String 3, open. Quarter note.
  Beat 2. Eighth rest.
  Beat 2 and. String 3, fret 3, to check. Eighth note.
  Beat 3. String 2, open. Eighth note.
  Beat 3 and. String 2, fret 2, hammer-on. Eighth note.
  Beat 4. String 1, open, let ring. Quarter note tied to whole note.

Bar 2
  Held from bar 1.
```

```text
Takt 1
  Slag 1. Streng 3, løs. Fjerdedelsnote.
  Slag 2. Åttendedelspause.
  Slag 2-og. Streng 3, bånd 3, bør sjekkes. Åttendedelsnote.
  Slag 3. Streng 2, løs. Åttendedelsnote.
  Slag 3-og. Streng 2, bånd 2, hammer-on. Åttendedelsnote.
  Slag 4. Streng 1, løs, la klinge. Fjerdedelsnote bundet til helnote.
```

- The words follow the talking score of the brass parts
  ([the spec](../../docs/accessibility/talking-score-spec.md)): bar headings, beat positions
  ("2 and", "2-og"), note values, and the Norwegian note names (H, B, Ess, Ass). The two languages
  are one table of word pairs in `src/instructions.rs`, chosen by `lang` as there. This crate does
  not use the talking score's code, which knows the brass band.
- **Said once, at the top:** the instrument and its number of strings (a mandolin's as pairs, each
  played and numbered as one string), how the strings are numbered, the tuning with its open strings from the highest-numbered string to string 1, the capo,
  the tempo and the time signature.
- **Strings are named by number,** never by note: the note names change with the tuning. Accidentals
  are words (`E-flat`, `Ess`), not signs.
- **One line per note, chord or rest,** in the order they are played: the beat, each note's string
  and fret (`open` for fret 0), and the note value. A chord says how many notes it has and names
  them from its highest-numbered string to its lowest.
- **Ties:** a held note is said once, where it starts, with every tied value. A bar that starts
  inside a held note says which bar it is held from.
- **Rests:** a rest inside a bar is a line; bars of rest that follow each other share one heading
  (`Bars 3–4`, `Rest, 2 bars.`).
- **Repeats:** a bar with the same lines as an earlier bar says `Same as bar 1.`
- **Techniques:** hammer-on, pull-off, slide and bend are said on the note they lead to, a slide and
  a bend with the fret they come from; vibrato, dead note and let ring on their own note (let ring
  where the ringing starts, once for a chord).
- **Doubt and range:** a doubtful note is `to check`; a note without a place is named by its pitch
  (`D 1, no string to play it on`).
- The two languages have the same lines in the same order: only the words differ.

## JSON

`json::solve_json` takes a request. It answers with:

- the instrument used;
- the fingering;
- the violations;
- for a preset instrument, `tuning_suggestions`: the presets of its family, ranked.

```json
{"instrument": {"preset": "guitar-standard", "capo": 2},
 "notes": [{"pitch": 62, "start": 0, "dur": 12}, {"pitch": 64, "start": 12, "dur": 12, "techniques": ["hammer-on"]}],
 "options": {"style": "open-position", "tempo_bpm": 96, "pins": [{"note": 0, "string": 2}]}}
```

`instrument` can also be a full `Instrument` object. A `preset` object takes only `capo`
alongside it.

`options` may be left out, and so may each of its fields, including each field of `hand`.

Unknown keys are errors, anywhere in the request: at the top, in the instrument, the options, a
note (so a misspelled `techniques` is refused, not dropped) and a given fingering. A note's keys
are the shared model's (`pitch`, `start`, `dur`, `confidence`, `sources`, `onset_s`, `offset_s`,
`performed_dur`, `articulations`, `trill`) and `techniques`. A malformed instrument is reported
with the field that is missing or unknown.

A passage has at most `MAX_NOTES` notes (20,000); a longer one is refused. Ten minutes of
sixteenth notes at 200 beats per minute are 8,000 notes, so the limit leaves room for a long piece
played in chords, and stops a request far beyond any piece before it costs seconds and hundreds of
megabytes: the solver keeps every candidate position of every note in memory.

`json::tab_json` takes the same request with what the page says added, and answers with
`{"musicxml": "...", "adjusted_notes": 0}`. `json::tab_musicxml_json` answers with the MusicXML text
alone.

```json
{"title": "Study", "instrument": {"preset": "guitar-standard", "capo": 2},
 "notes": [{"pitch": 66, "start": 0, "dur": 24, "confidence": 0.3}],
 "tempo_bpm": 96, "meter": {"beats": 3, "beat_unit": 4}, "key": {"fifths": 2, "mode": "major"},
 "tab": {"layout": "tab", "doubt_below": 0.4, "capo": "tuning", "clef": "treble-8vb"}}
```

- Every field but `instrument` and `notes` may be left out: 4/4, C major, `tab-and-notation`.
  The tempo is `tempo_bpm`, else `options.tempo_bpm`, else 120.
- Without `fingering` the notes are solved with `options` first. With `fingering` (the `fingering`
  of an earlier answer, perhaps edited) they are written where it says, once each place is checked
  to sound its note on the instrument; a place that does not is an error.

`cargo run -p target-fretted --example tab < request.json` prints the document for a request.

`json::tab_text_json` and `json::playing_instructions_json` take the same tab request and answer
with plain text, not JSON: the text tab and the playing instructions. They read one more key,
`"text": {"width": 72, "lang": "en"}` (each field may be left out); the other writers accept the key
and do not read it. `tab.doubt_below` decides the `?` and the "to check" as it does in the MusicXML;
`tab.layout`, `tab.capo` and `tab.clef` have no meaning in text.

The same requests and answers reach the apps through the bindings in `brasscribe-ffi`
(`fretted_fingering_json` for `solve_json`, `fretted_tab_json` for `tab_json`,
`fretted_tab_text_json` and `fretted_playing_instructions_json` for the two texts; see
[the core's README](../README.md#bindings)) and the command line (`brasscribe-core fret`, and `tab`
with `--format json`, `text` or `instructions`, where `--lang` and `--width` stand in for the
request's `text`). Every refusal is invalid input there.

## Not modelled yet

- **Sustain without let ring.** A note without `let-ring` may be cut by a later note on its string.
- **Held notes and the hand span.** Only notes that start on the same tick count as one event for
  the span.
- **Guitar chord shapes beyond power chords.** There is no CAGED table, and no finger count or barre
  model. Guitar open chords come from the span, height and open-string terms.
- **Vibrato** has no position constraint.
- **String crossing.** Skipping strings costs nothing.

Known limits of the text exports:

- The text tab shows where notes start, not how long they last: there is no rhythm line under it.
- The text tab is written in English. The playing instructions know English and Norwegian Bokmål.
- A tuning's name is kept as it is in Norwegian ("B standard", "Drop B"); the open strings after it
  are named the Norwegian way.
- The playing instructions name no chord shapes ("G chord, open"): a chord is its strings and frets.

Known limits of the MusicXML:

- **One rhythmic voice.** A chord is cut when the next note starts, so a bass note held under a
  melody loses its length. There is no second voice.
- **Bends.** The model has no bend amount, and the solver gives the bent note the fret that sounds
  its pitch. The bend is written on the note it starts from and the bent note follows as its own
  number, so a reader that plays bends sounds the target pitch twice. Pre-bends and releases are
  not written.
- Meter and key changes, chord names and diagrams, palm mute, harmonics and a per-string (partial)
  capo are not written.

The weights are hand-set against the tests below. They have not been fitted to a tab corpus.

## Tests

```sh
cd core
cargo test --profile fast -p target-fretted
cargo clippy -p target-fretted --no-deps --all-targets -- -D warnings
```

`tests/fingering.rs` covers:

- **Properties** over random passages on every preset, with and without a capo:
  - output pitch equals input pitch;
  - out-of-range notes are flagged, never moved;
  - the same input always gives the same output;
  - playable input (built from positions that fit the hand) gets zero violations.
- **Scales and lines:**
  - a first-position C major scale stays in frets 0 to 4;
  - the same melody an octave up, and a twelfth-fret lick, are not written on open strings or low
    frets.
- **Chords:**
  - open G, C, D, Em and Am come out as the standard shapes, alone and as a progression;
  - the same shapes a whole step up with capo 2 come out as the same frets relative to the capo.
- **Instruments:**
  - high-G and low-G ukulele;
  - E♭ standard against standard;
  - low B on a 5-string bass.
- **Pins, repeats and edge cases:**
  - pins, including one that reflows a chord and one that cannot be honoured;
  - repeated phrases;
  - more notes than strings;
  - doublings;
  - the JSON round trip.

`tests/shapes_tunings_techniques.rs` covers:

- **Chord shapes:**
  - power chords: C5 `x-3-5-5`, the C5 dyad and drop-D G5 `5-5-5` in every style, plus a riff of
    power chords;
  - ukulele G, Am, F and C on high and low G, and with a capo;
  - mandolin G and D.
- **Tuning suggestion:**
  - a bass line down to D1 is flagged in standard, gets drop D suggested, and plays cleanly in
    drop D, also through JSON;
  - an E♭ riff ranks E♭ standard ahead of drop D, on guitar and on bass;
  - ordinary material stays in standard: Ode to Joy, a C scale from C3, a melody down to D3, and
    a bass line down to D2;
  - a line that fits standard ranks standard first;
  - BEAD, drop D, drop B and the 7-string E♭ tuning each rank first for a line that needs them.
- **Techniques:**
  - hammer-ons, pull-offs, slides and bends stay on the string;
  - a bend moves off an open string, and a bent note can also ring;
  - legato beyond its reach is reported as `technique-reach`;
  - let ring keeps later notes off its string, both at the next onset and further on;
  - the check reports each broken constraint;
  - techniques are read from JSON notes, and other spellings are refused.
- **Position:** E minor pentatonic licks at the 12th fret stay in frets 12 to 15.

`tests/tab_musicxml.rs` covers the MusicXML. Every document is parsed back, and whole measures are
checked to hold exactly their length on each staff.

- **Tab staff:** line count and `<staff-tuning>` lines for standard and drop-D guitar, 4- and
  5-string bass, both ukuleles and mandolin; flat tunings; both capo encodings.
- **Out of range:** a rest and the note's name on the tab staff, the note on the notation staff, and
  no pitch on the tab staff without a string and fret that sound it.
- **Layouts:** two staves with the same notes, tab alone with stems and beams, notation alone; the
  clef of every preset, and of a custom instrument with and without `notation`.
- **The grid:** starts and lengths off the grid in 9/8, 6/8 and 4/4 are moved and counted, every
  note has a type, and every triplet value sits in a bracket that opens and closes on its staff.
- **Refusals:** time signatures, keys, tempos and hand-built notes that cannot be written; control
  characters in names.
- **Rhythm:** ties across the bar line, rests, pickups, triplets, compound time (beams and values
  on the dotted quarter, no tuplets), chords, a chord cut
  at the next note, doublings.
- **Techniques:** start and stop pairs, marks at the ends of a tied note, each technique's element.
- **Doubt and range:** the colour, the confidence, the `?` and the `!`, the threshold, never a
  parenthesis, and no change to pitch or place.
- **The note index:** one on every note with a pitch and none on a rest, the same on every tied
  piece and on both staves, every placed note named, a moved note, a chord, a note without a place
  and a doubling.
- **Whole documents:** a fixed pseudo-random passage on every preset, in four meters and three
  layouts; the same input gives the same text; the JSON entry point.
- **Fixture:** `tests/fixtures/study.json` (an original four-bar study with every feature) must give
  `tests/fixtures/study.musicxml`. Regenerate it on purpose with the `tab` example.

`tests/tab_text.rs` covers the text tab and the playing instructions:

- **What they look like:** a bass line and guitar chords as whole documents; the lines and labels of
  every instrument family; the legend; `let ring` in its three forms; a bar wider than the page; a
  line in both languages.
- **Properties** over made-up passages on every preset, with chords, rests, ties over bar lines,
  triplets, frets above 9, every technique, doubtful notes, notes without a place and pickups:
  - bar for bar, the numbers on the lines are the notes of the MusicXML tab staff where they start,
    each once, at three page widths; a `?` and a `!` per marked column, and each note without a
    place named once;
  - all lines of a system have one length, bar lines stand under each other, every number starts a
    whole cell from the bar line, and marks and bar numbers stand over their column;
  - no line is longer than the page, the bars are the same at every width, and a bar is only
    divided when it is wider than the page;
  - the same score gives the same text;
  - the instructions in the two languages have the same headings, blank lines and lines, and bar
    for bar say the notes of the tab staff, each once.
- **Refusals:** widths and languages that cannot be written, the doubt threshold, unknown keys in
  `text`, and more notes than `MAX_NOTES`.

Unit tests in `src/instrument.rs` cover positions, the capo, short strings, fret distances and
families. Unit tests in `src/shapes.rs` cover the shape tables.
