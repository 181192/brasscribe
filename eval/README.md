# brasscribe-eval

Dataset builders, benchmarks and the regression gate behind `brasscribe bench`.

```
pixi run brasscribe bench list          # all suites
pixi run brasscribe bench cpu           # every CPU suite on the local data directory
pixi run brasscribe bench <suite>[,<suite>...]
```

Suites score model outputs that already exist next to the eval data (`--mode cached`, the
default). They compare each metric with `eval/baselines.json` (numbers from
`docs/research/10-benchmark-results.md`, ±0.01 unless a metric sets its own tolerance). A
suite without its data is reported as skipped, never as passed; `--require-data` turns a skip
into a failure.

## What gates where

CI (`.github/workflows/ci.yml`, Ubuntu 24.04) runs `brasscribe bench ci --require-data` on data
built by `python -m brasscribe_eval.ci_data --out ci-data`:

- ChoraleBricks v1.1.0 annotations (CC-BY 4.0, [Zenodo 10.5281/zenodo.20849469](https://zenodo.org/records/20849469)):
  `metadata_tracks.csv` and the alignment CSVs of the brass-quartet tracks, read out of the
  archive with HTTP range requests (about 2 MB, no audio). Every file and every rebuilt
  `reference.json` is checked against the sha256 pinned in `eval/fixtures/choralebricks-pins.json`.
- `eval/fixtures/choralebricks-brass4/`: our own adapter outputs on those chorales
  (MuScriptor medium/large with and without brass conditioning, Basic Pitch as recorded and retuned to
  A = 440 as the brass-band profile runs it, Beat This!).
- `eval/fixtures/contours/`: SwiftF0 contours of the ChoraleBricks part tracks.
- `eval/fixtures/choralebricks-solo/`: SwiftF0 and Basic Pitch MIDI and Beat This! small0 beats of
  all 93 ChoraleBricks brass stems (trumpet, flugelhorn, French horn, trombone, baritone, tuba), with
  each stem's ChoraleBricks note annotation (`<stem>.notes.csv`, CC-BY 4.0, same source as above).
- `eval/fixtures/fast-notes/`: fast runs, repeated notes and two-note alternations rendered from real trumpet
  samples (University of Iowa MIS, VSCO 2 CE; dry and with an OpenAIR church response), with their exact
  reference, oracle beats, and our SwiftF0, Basic Pitch and Beat This! small0 outputs (`fast_notes.py`;
  docs/plan/fast-notes.md).

| Suite | CI | Local only because |
|---|---|---|
| chorales-transcription | yes | |
| quant-chorales | yes | |
| consensus-chorales, consensus-chorales-retuned | yes | |
| solo-instruments, seat-voices | yes | |
| fast-notes | yes | |
| quartet-audio | yes | |
| arrange | chorales part | URMP part: URMP licence not checked for redistribution |
| durations | chorales part | URMP part: as above |
| freetime | chorales part | URMP part and the combined means: as above |
| urmp-transcription, quant-urmp, consensus-urmp | no | URMP |
| slakh-transcription, consensus-slakh | no | Slakh licence not checked for redistribution |
| melody | no | needs URMP and Slakh |
| solo-vote | no | needs Slakh and the Mega-53 stems of every case |
| solo-ondevice | no | the URMP Entertainer clip and the on-device reference run |
| bass-tab | no | Slakh; its low-register part is synthesized here (FluidSynth, MuseScore General) and needs the models' outputs on it. `python -m brasscribe_eval.bass_tab_bench build`, `synthesize` and `prepare` make the set, `brasscribe bench bass-tab` scores it |
| guitar-tab | no | GuitarSet (CC BY 4.0, 1.4 GB with the audio: Zenodo 3371780, `annotation.zip` and `audio_mono-mic.zip` unpacked under `data/guitarset/`) and Slakh, and the models' outputs on both. `python -m brasscribe_eval.guitar_tab_bench build`, `prepare`, `build-songs` and `prepare-songs` make the sets, `brasscribe bench guitar-tab` scores them. Its rules were set on players 00 to 02 and are quoted for players 03 to 05. The player's string is counted two ways: `string_agreement` over the notes the tab has right, `string_recall` over all the notes played. Guitars in a song are Slakh's, with the songs that have one guitar also reported apart (`song_one`). Where IDMT-SMT-Guitar is unpacked (CC BY-NC-ND 4.0, 1.3 GB: Zenodo 7544110, under `data/idmt-smt-guitar/`; `build-idmt` and `prepare-idmt` with its folder) its licks and pieces are scored too: two of its three guitars with the material the rules are chosen on, the third and the pieces only reported |
| ukulele-tab, mandolin-tab | no | passages written in `small_tab_bench.py` and rendered with FluidSynth and the MuseScore General SoundFont (its Ukulele and Mandolin presets), and the models' outputs on them: `python -m brasscribe_eval.small_tab_bench synthesize` and `prepare`, then `brasscribe bench ukulele-tab,mandolin-tab`. No recording of either instrument with its notes annotated was found, so this is all the evidence there is. Each group has a `heldout` one (other chords, scales and tempos, and a melody high on the top string over a ringing chord) that is reported, not tuned on, except the threshold of the ukulele's overtone rule above the 12th fret, which was tried against it too. Its chord-melody and strummed passages were used to choose the rule that tells a chord heard again under a melody from a strum struck again (engine `tab.py`, `RING_*`): they are scored apart, as development passages, under `<group>_heldout_dev`, and `<group>_heldout` holds the group's other passages (melody, picked). The split is `DEVELOPMENT` in `small_tab_bench.py`, and the rendered guitar's held-out groups have it too |
| meter-tab | no | eight passages written in `meter_tab_bench.py` and rendered (FluidSynth, MuseScore General), one instrument alone in 2/4, 3/4, 6/8, 12/8 and 5/4: the beats in a bar as the tracker found them and as the tab profiles write them. `python -m brasscribe_eval.meter_tab_bench synthesize` and `prepare`, then `brasscribe bench meter-tab` |
| guitar-rendered-tab | no | the same bench with a guitar: open chords picked and strummed and a melody, nylon, steel and clean electric presets. Two groups were used to choose the overtone rules; the two `heldout` groups (other chords, tempos, one other preset) are only reported. `brasscribe bench guitar-rendered-tab` |
| mikkel-golden, readability, musescore-roundtrip | no | Mikkel is a commercial recording; the round trip also needs MuseScore |

On a machine with the full `data/` directory, `brasscribe bench cpu` runs all of them.

Refreshing the fixtures after a deliberate model or dataset change: copy the new outputs into
`eval/fixtures/`, run `python -m brasscribe_eval.ci_data --pin` (it rebuilds every reference from
the local ChoraleBricks copy and checks it against `data/eval`), and update the baselines together
with the doc.
