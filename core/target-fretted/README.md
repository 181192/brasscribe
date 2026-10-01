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
| `guitar-drop-d` | E4 B3 G3 D3 A2 D2 | 22 | 648 mm |
| `guitar-drop-c` | D4 A3 F3 C3 G2 C2 | 22 | 648 mm |
| `guitar-dadgad` | D4 A3 G3 D3 A2 D2 | 22 | 648 mm |
| `guitar-open-g` | D4 B3 G3 D3 G2 D2 | 22 | 648 mm |
| `guitar-open-d` | D4 A3 F♯3 D3 A2 D2 | 22 | 648 mm |
| `guitar-open-e` | E4 B3 G♯3 E3 B2 E2 | 22 | 648 mm |
| `guitar-7-standard` | E4 B3 G3 D3 A2 E2 B1 | 24 | 648 mm |
| `guitar-8-standard` | E4 B3 G3 D3 A2 E2 B1 F♯1 | 24 | 686 mm |
| `bass-4-standard` | G2 D2 A1 E1 | 21 | 864 mm |
| `bass-5-standard` | G2 D2 A1 E1 B0 | 24 | 864 mm |
| `bass-6-standard` | C3 G2 D2 A1 E1 B0 | 24 | 864 mm |
| `ukulele-high-g` | A4 E4 C4 G4 (concert) | 18 | 380 mm |
| `ukulele-low-g` | A4 E4 C4 G3 (concert) | 18 | 380 mm |
| `ukulele-baritone` | E4 B3 G3 D3 | 19 | 483 mm |
| `mandolin` | E5 A4 D4 G3 | 20 | 350 mm |

`ukulele(UkuleleSize::Soprano | Concert | Tenor, low_g)` builds the other ukulele sizes: 330, 380
and 432 mm. A custom tuning is just another `Tuning`.

## How notes are placed

Notes that start on the same tick form an **event**. Notes of the same pitch in one event (a
doubling from two voices) sound as one note and share a position.

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

Per transition from one event to the next:

- **Shift.** A fixed cost per hand move plus a cost per mm moved. Both are scaled by
  `1 + 0.25 s / Δt`, so a shift with no time to make it costs more. Ticks become seconds through
  `Options::tempo_bpm`. Without a tempo, time is counted in beats, as at 120 BPM.
- **Dropping below the hand.** In a single-note line, a note more than a hand's width (three frets)
  below the neighbouring hand position costs extra, per mm of the drop. This is the
  "twelfth-fret solo written as open strings" failure: a line played up the neck should not dip to
  an open string or a first-position fret on a thin string for one note.

Style presets (`Style`) re-weight these terms:

| Style | Height | Open strings | Shifts |
|---|---|---|---|
| `OpenPosition` | strongest pull to the nut | bonus in chords and lines | normal |
| `AsPlayed` (default) | mild | small bonus in chords, neutral in lines | normal |
| `Lead` | almost none | penalty in single-note lines | doubled, so a phrase stays in one position |

The weights are in one table in `src/solve.rs`.

**Repeats.** When a run of four events has the same pitches as an earlier run, a second pass makes
the repeat, and the first occurrence, keep the first occurrence's fingering. A strong cost for
deviating does this, so a pin or an impossible reuse still wins.

**Pins.** `Options::pins` fixes the string of a note. The solver treats a pin as a hard constraint,
and the neighbours and the rest of a chord reflow around it. A pin on a string that cannot sound the
pitch is ignored by the solver and reported by the check.

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
  instrument (`no-string`).

## JSON

`json::solve_json` takes a request and answers with the instrument used, the fingering and the
violations.

```json
{"instrument": {"preset": "guitar-standard", "capo": 2},
 "notes": [{"pitch": 64, "start": 0, "dur": 24}],
 "options": {"style": "open-position", "tempo_bpm": 96, "pins": [{"note": 0, "string": 2}]}}
```

`instrument` can also be a full `Instrument` object. A `preset` object takes only `capo`
alongside it.

`options` may be left out, and so may each of its fields, including each field of `hand`.

Unknown keys are errors, anywhere in the request. A malformed instrument is reported with the
field that is missing or unknown.

## Not modelled yet

- **Let-ring and sustain.** A note still sounding when the next starts does not reserve its string.
- **Technique constraints.** Bends, slides and hammer-ons do not force a fretted note or a shared
  string.
- **Chord shapes.** There is no table of idiomatic shapes (CAGED forms, power chords). There is no
  finger count or barre model either. Open chord shapes come from the span, height and open-string
  terms.
- **String crossing.** Skipping strings costs nothing.
- **Tuning suggestion** from the range of the notes.
- **Sustained notes.** Only notes that start on the same tick count as one event for span and
  shared strings.

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

Unit tests in `src/instrument.rs` cover positions, the capo, short strings and fret distances.
