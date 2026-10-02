# core: the Rust port of the symbolic pipeline

One implementation of the symbolic logic for every native app, bound to Swift
and Kotlin with UniFFI and to C# through a C ABI. The Python code stays the
reference (`music/`, the `eval/` entry points, `sounds/humanize.py`,
`engine/.../talking_score.py`); `conformance/` checks that this port produces
identical Compositions, MusicXML, humanized notes and talking scores.

```
brasscribe-core/   pure logic (deps: serde, serde_json, roxmltree)
  model            Composition + composition.json (field order and number format of the reference)
  quantize         beat map, metrical level, grids (free-time grids, dense grids for fast runs), fill_gaps
  onsets           pitch-change onsets from the SwiftF0 contour (trills, runs, octave flips, bends)
  rhythm_spelling  split and tie values so a part shows the beat
  freetime         unstable beat runs -> synthetic beats, FreeRegions, clipping, fermatas
  durations        contour offsets, written durations, staccato
  spelling         ps13 pitch spelling, Krumhansl-Kessler key
  harmony          harmonic-rhythm reduction
  instruments      brass-band instruments (Trumpet in B♭ included), lineups (band, minimal, quartet) with their roles,
                   ranges, transpositions; the players' seats with the clef each reads and the part it takes
  arranger         minimal band or quartet (`arrange_opts`) and solo with band (`arrange_layers_opts`: lineup, soprano
                   doubling, figuration); `voice_satb` voices the quartet's alto and tenor
  difficulty       faithful / standard / easier rewrites of the arranged parts
  keys             key plan (key changes, modes), transposition to a concert key
  beats, energy, separation, dynamics, structure
                   beat cleanup, solo meter and bar phase, energy gate, separation check, dynamics, rehearsal marks
  confidence       calibrated solo-note confidence (logistic model, calibration.json) and review groups
  humanize         deterministic playback humanization (sounds/README.md)
  talking_score    talking score: document from MusicXML, announcer, navigation, text/HTML export
  consensus, lines note voting across transcriptions, monophonic lines
  midi             SMF reading with pretty_midi's note semantics
  py, pyjson       CPython/NumPy rounding, sums and JSON output, bit for bit
  pipeline         the reference entry points (arrange_layers_song, arrange_song, lead_sheet, reference -> band)
  notation/        measures, accidentals, ties, tuplets, beams, stems, transposition, MusicXML
brasscribe-ffi/    UniFFI exports + `bc_*` C ABI (the core, and target-fretted as JSON)
brasscribe-cli/    `brasscribe-core` binary: the same entry points as the Python scripts, file based
target-fretted/    tab fingering: a string and fret for every note on guitar, bass, ukulele, mandolin
bindings/          generated Swift, Kotlin and C header (scripts/bindings.sh)
swift/BrasscribeCore  SwiftPM package (binaryTarget XCFramework + generated Swift)
android/           Android library (AAR) with jniLibs per ABI, JVM smoke test
dotnet/            Brasscribe.Core (P/Invoke) + xunit tests
conformance/       Python/uv runner: reference vs Rust on the golden and eval inputs
scripts/           bindings.sh, build-all.sh
```

## Commands

Needs Rust stable, and `uv` for the conformance runner.

```sh
export PATH=/opt/homebrew/opt/rustup/bin:$PATH
cargo build --release                      # brasscribe-core CLI at target/release/brasscribe-core
cargo test --release                       # unit tests + fixtures from the Python reference
cd conformance && uv run python -m brasscribe_conformance.run [--musescore] [--only mikkel]
uv run python -m brasscribe_conformance.fixtures   # regenerate the unit fixtures
scripts/bindings.sh                        # Swift/Kotlin/C bindings
scripts/build-all.sh                       # macOS, iOS, iOS simulator, Android, Windows, XCFramework
cd swift/BrasscribeCore && swift test      # (DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer)
cd dotnet/Brasscribe.Core.Tests && dotnet test
android/smoke/run.sh                       # Kotlin bindings on the JVM against the macOS library
cd android && gradle :brasscribe-core:assembleRelease   # AAR
```

CLI (mirrors `eval/brasscribe_eval/*.py`):

```sh
brasscribe-core arrange-layers --layers data/mikkel/repro/layers --beats data/mikkel/repro/mix.beats \
    --solo-contour <solo-sw.contour.npz> --out out/ --title "Mikkel"
brasscribe-core arrange-song --beats b.beats --melody m.mid --melody-support bp.mid --bass m.mid --harmony m.mid bp.mid --out out/
brasscribe-core lead-sheet --beats b.beats --melody m.mid --melody-support bp.mid --bass m.mid --out lead.musicxml
brasscribe-core arrange-reference --reference reference.json --out out/
brasscribe-core musicxml --composition composition.json --out band.musicxml
brasscribe-core humanize --notes notes.json --part "Solo Cornet" --player 0 [--composition c.json] [--timing performed] --out h.json
brasscribe-core talking-score --musicxml band.musicxml --composition c.json --text t.txt --html t.html --json t.json [--lang nb]
brasscribe-core quantize --reference reference.json --beats b.beats --out q.json
brasscribe-core meter --beats b.beats --notes notes.json --out meter.json
brasscribe-core normalize --composition composition.json --out composition.json
brasscribe-core fret --request request.json --out fingering.json
brasscribe-core tab --request tab-request.json --out tab.json
brasscribe-core tab --request tab-request.json --out tab.txt --format text [--width 72]
brasscribe-core tab --request tab-request.json --out instructions.txt --format instructions [--lang nb]
brasscribe-core version
```

`arrange-layers` also takes `--lineup band|full|minimal|quartet`, `--difficulty
faithful|standard|easier`, `--key Bb` or `--transpose N`, `--no-gate`,
`--no-beat-cleanup`, `--single-key`, `--no-free-time` and `--free-tempo BPM`, the player's seat
(`--seat trumpet`, `--reads` for the clef they read, `--lead lineup|seat`: `seat` gives the seat the
tune) and `--lang nb` for the source footer on each part, and reads the stems
(`solo.wav`, `bass.wav`, `drums.wav`, `orchestra.wav`) from the layers folder
when present. `arrange-song` and `arrange-reference` take `--lineup
minimal|quartet` (default minimal); `arrange-song` also takes `--seat`, `--reads` and `--lead`. The quartet is 1st Cornet, 2nd Cornet,
Tenor Horn and Euphonium, one player each.

`fret` is how the engine reaches [`target-fretted`](target-fretted/README.md): it reads that crate's JSON request
(instrument, notes, options) and writes its JSON response (fingering, violations, tuning suggestions), both unchanged.
`tab` does the same for tablature: the crate's tab request in (the notes, a fingering or none, title, tempo, meter,
key, and `tab` with the layout, the capo encoding and the doubt threshold), and `{"musicxml": …, "adjusted_notes": …}`
out.

## Conformance

`conformance/` runs each case through the Python entry point and the CLI and
compares the outputs:

- **composition.json** and the other JSON outputs: byte-equal. Where they differ, the report names
  the first value that differs when parsed, strictly: types (`1` is not `1.0`, `true` is not `1`),
  floats bit for bit (`-0.0` is not `0.0`) and key order.
- **MusicXML**: canonicalised, then byte-equal. Canonicalisation only drops
  comments, whitespace between elements, `<encoding-date>` and `<software>`,
  renumbers `id` attributes in order of first appearance, and writes C14N.

Cases: the Mikkel layers (with the SwiftF0 contour) and its option variants
(standard, easier, minimal + easier, key B♭, transposed down 3), and for every song in
`data/eval/*` the song arrangement, the lead sheet, synthetic layers (the
song's full-mix transcriptions as every layer), the arranger benchmark
(reference notes, where they carry notated positions) and quantization of the
reference notes. Every arranged case also compares the talking score (document
JSON, text and HTML under four settings) and humanization (every voice as a
part, on and off its ticks, two players, score and performed timing, with and
without the Composition) against their Python references. The Mikkel case is
compared file by file with `data/golden/mikkel-arranged-band`, parts and
talking score included; braille (`.brf`, music21's translator) is not ported. A case
whose golden output is missing fails, and so does a run that selects no case. The Rust
side, and the reference whenever it runs, write into emptied directories, so no file left
by an earlier run is compared.
`uv run python -m unittest discover -s tests` checks the comparisons themselves.
The talking score also passes every vector in
`docs/accessibility/talking-score-vectors.json` (`cargo test`, and the .NET
tests through the C ABI). Results go to `data/runs/core-conformance/report.json`.

Reproducing the reference bit for bit needed its numeric details, all covered
by unit fixtures: NumPy's `interp` is compiled with FMA; `np.sum` is pairwise
(float32 for the key profile); `np.round` and Python's `round` differ and
both are used (NumPy scalars vs Python floats); ps13 orders equal pitches
with NumPy's unstable introsort; music21's notation rules (accidental display,
tuplet completion and brackets, beam partials, stems per beam group,
transposed accidentals, MIDI channel assignment) are ported in `notation/`.

Each band case also checks the app path: the reference `composition.json` read
back by Rust gives the same bytes, and arranging it (`brasscribe-core
musicxml`) gives the reference MusicXML.

Open points:

- The reference is pinned to the machine it runs on (macOS arm64, NumPy
  2.5.3, music21 10.5.0, partitura 1.9.0). On x86 with AVX2/AVX-512 NumPy's
  argsort takes another code path (x86-simd-sort) and orders ties
  differently, and builds without FMA contraction round `interp` differently,
  so a Linux CI reference may not agree with this one.
- MuseScore rejects two reference scores (synthetic layers of URMP 31 and 34)
  that the port reproduces exactly: a triplet-quarter written length followed
  by a rest music21 writes as a 24:13 tuplet.

## Bindings

Swift (UniFFI):

```swift
import BrasscribeCore
let xml = try arrangeMusicxml(compositionJson: json, arranger: "auto")
// Re-arrange for a lineup and difficulty (transpose: the total from the recording)
let quartet = try arrangeMusicxmlWith(compositionJson: json,
                                      options: ArrangeOptions(lineup: "quartet", difficulty: "easier", key: nil, transpose: nil))
let out = try arrangeLayersSong(layers: LayerMidi(soloSwiftf0: sw, soloMuscriptor: mus, soloBasicPitch: bp,
                                bass: bass, orchestra: orch, drums: drums),
                                beatsText: beats, title: "Mikkel", soloContour: nil, freeTime: true, freeTempo: nil)
```

Kotlin (UniFFI, JNA):

```kotlin
import uniffi.brasscribe_ffi.*
val xml = arrangeMusicxml(json, "auto")
val spelled = spellPitches(listOf(0.0, 1.0), listOf(66, 69))
```

Band arrangement with stems and options, humanization and the talking score (Swift):

```swift
let band = try arrangeLayersBand(layers: midi, stems: LayerStems(solo: soloWav, bass: bassWav, drums: drumsWav, orchestra: orchWav),
                                 beatsText: beats, title: "Mikkel", options: layersSongDefaults())
let perf = try Performance(compositionJson: band.compositionJson)
let played = try humanizePart(notes: notes, part: "Solo Cornet", player: 0, seed: "brasscribe", performance: perf, performedTiming: false)
let ts = try TalkingScore(musicxml: band.musicxml, compositionJson: band.compositionJson)
var cursor = TalkingCursor(part: 1, bar: 0, event: 0)
let line = try ts.announce(cursor: cursor, context: TalkingContext(), settings: talkingSettingsDefault(), byBar: false)
cursor = ts.navigate(cursor: cursor, unit: .note, forward: true) ?? cursor
```

C# (P/Invoke over `bc_*`):

```csharp
using Brasscribe.Core;
string xml = BrasscribeCore.ArrangeMusicXml(compositionJson);
string quartet = BrasscribeCore.ArrangeMusicXmlWith(compositionJson, lineup: "quartet", difficulty: "easier");
var band = BrasscribeCore.ArrangeLayersBand(layers, new LayerStems(solo, bass, drums, orchestra), beatsText, "Mikkel",
                                            new LayersSongOptions(Difficulty: "easier"));
var played = BrasscribeCore.Humanize(notes, "Solo Cornet", 0, compositionJson: band.CompositionJson);
using var ts = new TalkingScore(band.MusicXml, band.CompositionJson);
var (text, context) = ts.Announce(new TalkingCursor(1, 0, 0), settings: new TalkingSettings(Lang: "nb"));
```

Tab fingering for fretted instruments ([`target-fretted`](target-fretted/README.md)) goes through
the bindings as that crate's JSON, the same request and answer as the command line's `fret` and
`tab`: `fretted_fingering_json` (instrument or preset, notes with their techniques, style and pins
in; the fingering with each note's alternatives, the violations and the tuning suggestions out) and
`fretted_tab_json` (the tab request in; `{"musicxml": …, "adjusted_notes": …}` out). They are
`frettedFingeringJson` and `frettedTabJson` in Swift and Kotlin, `BrasscribeCore.FrettedFingeringJson`
and `FrettedTabJson` in C#, and `bc_fretted_fingering_json` and `bc_fretted_tab_json` in C.
`fretted_tab_text_json` and `fretted_playing_instructions_json` take the same tab request and answer
with plain text: the tab for a monospace font (`"text": {"width": 72}`), and the tab in words for a
screen reader or a braille display (`"text": {"lang": "en"}` or `"nb"`). Their names follow the same
pattern in each language (`frettedTabTextJson`, `BrasscribeCore.FrettedPlayingInstructionsJson`,
`bc_fretted_tab_text_json`).

```kotlin
val answer = frettedFingeringJson("""{"instrument": {"preset": "bass-4-standard"},
    "notes": [{"pitch": 33, "start": 0, "dur": 24}], "options": {"pins": [{"note": 0, "string": 4}]}}""")
// {"instrument": {…}, "fingering": {"notes": [{"pitch": 33, "string": 4, "fret": 5, "alternatives": [{"string": 3, "fret": 0}],
//   "out_of_range": false, "pinned": true}]}, "violations": [], "tuning_suggestions": [{"preset": "bass-4-standard", …}, …]}
```

C: `bindings/c/brasscribe.h`. Strings are NUL-terminated UTF-8; every call
returns 0 or an error code (1 invalid input, 2 failure, 3 null argument,
4 internal error) and writes the result to `*out` or a message to `*err`;
free returned strings with `bc_string_free`.

### Invalid input

The bindings check what they are given before any work starts, and answer
with invalid input (`CoreError::Invalid`, `BC_INVALID`) rather than a failure,
a panic or a hang:

- a Composition (`Composition::validate`): meters of 1 to `MAX_BAR_BEATS`
  beats with a note-value beat unit, notes of non-negative length with MIDI
  pitches 0-127, beat times in order, and everything within `MAX_BEATS` of
  tick 0 (the longest piece the core arranges); a recording that arranges to
  more than that fails with the same message;
- a beat table: times and positions are numbers and the times increase;
- options: unknown lineups, difficulties, seats, clefs, leads, languages and
  keys, a transposition beyond `MAX_TRANSPOSE` semitones or out of MIDI range,
  a free-time tempo outside `FREE_TEMPO_RANGE`;
- a fretted request: JSON that is not the request (unknown keys included, also in a note), an
  unknown preset, style or technique, a pin that names a note or a string that does not exist,
  more than 20,000 notes, a note outside MIDI 0-127 or `MAX_BEATS`, a given fingering with a string
  and fret that do not sound its note, and for tablature a meter, key, tempo or note length that cannot be
  written. A pin on a string that cannot sound its note is not invalid: the answer lists it under
  `violations`;
- a solo contour whose arrays differ in length (a JSON `null` in an array is a
  frame without a value, not a missing frame), a WAV stem with a cut-off
  format chunk, list arguments of different lengths, and times that are not
  numbers.

## Test tiers

| Tier 1 (inner loop) | Tier 2 (before handoff) | Tier 3 (devices, UI) |
| --- | --- | --- |
| `cargo test --profile fast` | `cargo test --release`, the full conformance run | none |

See [docs/dev/verify.md](../docs/dev/verify.md).
