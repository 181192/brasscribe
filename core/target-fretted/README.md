# target-fretted

Tablature fingering for fretted instruments. It chooses a string and a fret for each note of a
passage, so the passage can be written as tab for guitar, bass, ukulele or mandolin.

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
length in millimetres and a capo.

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
2. the lowest open string fits the lowest note: the same note, or the same pitch class an octave or
   more below it (`low_string_fits`);
3. most notes an open string can play (`open_notes`);
4. fewest notes that can only be played above the 12th fret;
5. closest to the standard tuning, as semitones summed over the open strings;
6. preset order.

Fit comes before closeness. So an E♭ riff ranks E♭ standard first, even though drop D is closer to
standard and also reaches its notes. A bass line that goes down to D1 ranks `bass-4-drop-d` first,
and a line that fits standard tuning ranks standard first. The JSON response carries this ranking for a preset instrument, so the song check
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
| `Lead` | almost none | penalty in single-note lines | also twice the cost per mm, so a phrase stays in one position | power chords only |

The weights are in one table in `src/solve.rs`.

**Repeats.** When a run of four events has the same pitches as an earlier run, a second pass makes
the repeat, and the first occurrence, keep the first occurrence's fingering. A strong cost for
deviating does this, so a pin or an impossible reuse still wins.

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

Names are kebab-case: `slide`, `hammer-on`, `pull-off`, `bend`, `vibrato`, `let-ring`.

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

Unknown keys are errors, anywhere in the request. A malformed instrument is reported with the
field that is missing or unknown.

## Not modelled yet

- **Sustain without let ring.** A note without `let-ring` may be cut by a later note on its string.
- **Held notes and the hand span.** Only notes that start on the same tick count as one event for
  the span.
- **Guitar chord shapes beyond power chords.** There is no CAGED table, and no finger count or barre
  model. Guitar open chords come from the span, height and open-string terms.
- **Vibrato** has no position constraint.
- **String crossing.** Skipping strings costs nothing.

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

Unit tests in `src/instrument.rs` cover positions, the capo, short strings, fret distances and
families. Unit tests in `src/shapes.rs` cover the shape tables.
