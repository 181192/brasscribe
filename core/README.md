# core: the Rust port of the symbolic pipeline

One implementation of the symbolic logic for every native app, bound to Swift
and Kotlin with UniFFI and to C# through a C ABI. The Python library in
`music/` stays the reference; `conformance/` checks that this port produces
identical Compositions and MusicXML.

```
brasscribe-core/   pure logic (deps: serde, serde_json)
  model            Composition + composition.json (field order and number format of the reference)
  quantize         beat map, metrical level, grids (free-time grids), fill_gaps
  freetime         unstable beat runs -> synthetic beats, FreeRegions, clipping, fermatas
  durations        contour offsets, written durations, staccato
  spelling         ps13 pitch spelling, Krumhansl-Kessler key
  harmony          harmonic-rhythm reduction
  instruments      brass-band instruments, lineups, ranges, transpositions
  arranger         minimal band (`arrange`) and solo with band (`arrange_layers`)
  consensus, lines note voting across transcriptions, monophonic lines
  midi             SMF reading with pretty_midi's note semantics
  pipeline         the reference entry points (arrange_layers_song, arrange_song, lead_sheet, reference -> band)
  notation/        measures, accidentals, ties, tuplets, beams, stems, transposition, MusicXML
brasscribe-ffi/    UniFFI exports + `bc_*` C ABI
brasscribe-cli/    `brasscribe-core` binary: the same entry points as the Python scripts, file based
bindings/          generated Swift, Kotlin and C header (scripts/bindings.sh)
swift/BrasscribeCore  SwiftPM package (binaryTarget XCFramework + generated Swift)
android/           Android library (AAR) with jniLibs per ABI, JVM smoke test
dotnet/            Brasscribe.Core (P/Invoke) + xunit tests
conformance/       Python/uv runner: reference vs Rust on the golden and eval inputs
scripts/           bindings.sh, build-all.sh
```

## Commands

```sh
export PATH=/opt/homebrew/opt/rustup/bin:$PATH
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
```

## Conformance

`conformance/` runs each case through the Python entry point and the CLI and
compares the outputs:

- **composition.json**: parsed JSON, floats bit-equal (the bytes are identical too).
- **MusicXML**: canonicalised, then byte-equal. Canonicalisation only drops
  comments, whitespace between elements, `<encoding-date>` and `<software>`,
  renumbers `id` attributes in order of first appearance, and writes C14N.

Cases: the Mikkel layers (with the SwiftF0 contour), and for every song in
`data/eval/*` the song arrangement, the lead sheet, synthetic layers (the
song's full-mix transcriptions as every layer), the arranger benchmark
(reference notes, where they carry notated positions) and quantization of the
reference notes. Results go to `data/runs/core-conformance/report.json`.

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
- The golden set predates the free-time and duration changes; the runner
  compares against it for information only.

## Bindings

Swift (UniFFI):

```swift
import BrasscribeCore
let xml = try arrangeMusicxml(compositionJson: json, arranger: "auto")
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

C# (P/Invoke over `bc_*`):

```csharp
using Brasscribe.Core;
string xml = BrasscribeCore.ArrangeMusicXml(compositionJson);
var (comp, musicXml) = BrasscribeCore.ArrangeLayersSong(layers, beatsText, "Mikkel");
```

C: `bindings/c/brasscribe.h`. Strings are NUL-terminated UTF-8; every call
returns 0 or an error code (1 invalid input, 2 failure, 3 null argument,
4 internal error) and writes the result to `*out` or a message to `*err`;
free returned strings with `bc_string_free`.
