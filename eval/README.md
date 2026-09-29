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
  (MuScriptor medium/large with and without brass conditioning, Basic Pitch, Beat This!).
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
| consensus-chorales | yes | |
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
| mikkel-golden, readability, musescore-roundtrip | no | Mikkel is a commercial recording; the round trip also needs MuseScore |

On a machine with the full `data/` directory, `brasscribe bench cpu` runs all of them.

Refreshing the fixtures after a deliberate model or dataset change: copy the new outputs into
`eval/fixtures/`, run `python -m brasscribe_eval.ci_data --pin` (it rebuilds every reference from
the local ChoraleBricks copy and checks it against `data/eval`), and update the baselines together
with the doc.
