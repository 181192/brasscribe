# brasscribe-music

Symbolic core: the `Composition` model, quantization, free-time detection,
written durations and articulation, spelling, arrangement and MusicXML export.

```
uv run pytest -q
```

## `composition.json`

Written by `Composition.to_json`, read by `Composition.from_json`. Everything is
at concert pitch. Time is in integer ticks, `ticks_per_beat` (24) per beat;
tick 0 is the first downbeat, so pickup notes have negative starts. Seconds are
kept alongside so the score can be aligned back to the recording.

Readers must ignore unknown keys and treat missing optional keys as their
defaults: files written before a field existed stay valid.

### Top level

| Field | Type | Meaning |
|---|---|---|
| `title` | string | |
| `voices` | Voice[] | |
| `meters` | `{tick, beats, beat_unit}`[] | time signatures from `tick` on |
| `keys` | `{tick, fifths, mode}`[] | key signatures from `tick` on (bar lines); `fifths` < 0 is flats. `mode` names the tonic as a degree of the signature's major scale: `major`, `dorian`, `phrygian`, `lydian`, `mixolydian`, `minor`, `locrian` (fifths 0 + `lydian` = F lydian) |
| `beat_times` | float[] | seconds of beat 0, 1, 2 …: the tick map. Beat `k` is tick `(k - first_downbeat) * ticks_per_beat`; between beats, time is linear. Inside a free region these beats are synthetic (see below) |
| `first_downbeat` | int | index into `beat_times` of tick 0 (may be negative when the first bar starts before the first detected beat) |
| `ticks_per_beat` | int | 24 |
| `free_regions` | FreeRegion[] | optional, default `[]` |
| `review` | `{voice, start, end, notes, very}`[] | optional, absent when empty. Neighbouring uncertain notes of one voice reviewed together: `[start, end)` ticks, `notes` marked notes in it, `very` when any is very unsure. The score shows one "?" per item (boxed when `very`) with a dashed bracket over items of more than one note. See *Confidence and review marks* |
| `sections` | `{tick, label}`[] | optional, default `[]`. Rehearsal marks (A, B, …; no I) at bar lines |
| `arrangement` | object | optional, absent for default options. `{lineup: band|minimal, difficulty: faithful|standard|easier, transpose_semitones}`: how the arrangement was made. Pitches and keys in the file are already transposed |
| `dynamics` | `{tick, layer, mark}`[] | optional, default `[]`. A marking (`pp` `p` `mp` `mf` `f` `ff`) for one textural layer from `tick` on; the parts playing that layer show it at their next note |

### Voice

| Field | Type | Meaning |
|---|---|---|
| `id` | string | |
| `role` | `melody` \| `countermelody` \| `harmony` \| `bass` \| `rhythm` | |
| `notes` | Note[] | |
| `instrument_hint` | string \| null | what the source instrument seemed to be; never binding |
| `layer` | string \| null | textural layer: `solo`, `strings`, `brass`, `keys`, `bass`, `drums` |

### Note

| Field | Type | Meaning |
|---|---|---|
| `pitch` | int | concert MIDI pitch (GM drum number in a `drums` layer) |
| `start` | int | ticks |
| `dur` | int | **written** duration in ticks |
| `confidence` | float 0–1 | calibrated probability that the note is right (solo notes; see *Confidence and review marks*) |
| `sources` | string[] | which transcribers or stages produced it |
| `onset_s`, `offset_s` | float \| null | performed onset and offset in seconds |
| `performed_dur` | int \| null | optional. **Performed** length in ticks: `offset_s - onset_s` mapped through the tick map. `null` = unknown |
| `articulations` | string[] | optional, default `[]`. Values: `staccato` (performed length under half the written one), `fermata` |

`dur` is what a player reads; `performed_dur` is what was played. They differ
when a note is released early (written long, marked staccato when under half)
or held into the next beat.

### FreeRegion

A passage in free time (*ad lib.*, *colla voce*) where no beat grid is imposed.

| Field | Type | Meaning |
|---|---|---|
| `start`, `end` | int | ticks, `[start, end)`. `end` is a bar line: the strict grid resumes there |
| `start_s`, `end_s` | float | the same span in seconds. `end_s` is the first beat of the stable grid |
| `tempo_bpm` | float | the local tempo the passage is notated at |
| `notation` | `proportional` \| `tempo` | `proportional`: `tempo_bpm` was estimated from the note stream; `tempo`: the user gave it |
| `label` | string | direction text written at the start, default `ad lib.` |

Inside a region `beat_times` holds evenly spaced synthetic beats at `tempo_bpm`
from `start_s`, so the tick map needs no special case: tick ↔ seconds is still
piecewise linear over `beat_times`, and positions in the region are
proportional to performed time. MusicXML marks the start with the label and a
tempo, the bar lines inside with dashed bar lines, and the resumption with
*a tempo*.

Notes that start inside a region end at its `end` at the latest, and the last
note of the melody that starts inside it carries a `fermata`.

## Modules for free time and durations

- `freetime.py`: `unstable_runs` (detection), `plan_free_time` (synthetic
  beats, bar rounding, resume downbeat), `clip_to_regions`, `mark_fermatas`.
  Thresholds: `RATIO_TOL`, `MIN_INTERVALS`, `MIN_SECONDS`, `MIN_CV`,
  `MIN_STABLE`, `TEMPO_RANGE`, `TARGET_IOI_BEATS`. The quantizer uses only
  `quantize.FREE_GRIDS` (quarters, 8ths) inside regions.
- `durations.py`: `contour_offsets` (note ends from a SwiftF0 contour;
  `SEPARATED_STEM` settings for separated stems) and `written_durations`
  (`LEGATO_RATIO`, `MAX_HELD_GAP`, `READABLE`, `STACCATO_RATIO`).

## Arrangement options

`arranger.arrange_layers(comp, lineup, difficulty)`; `difficulty.py` holds the modes:

| Mode | Rhythm | Range | Also |
|---|---|---|---|
| `faithful` | as arranged | reading range preferred | the default; no soprano doubling or figuration |
| `standard` | 16th pairs merged into 8ths where the dropped note is not a chord tone | every part folded into its reading range | Soprano Cornet doubles the solo an octave up at climaxes; pads and choir re-attacked at the source's 8th-grid attacks |
| `easier` | non-solo parts on an 8th grid; the solo's 16th pairs merged keeping its turning points | every part in its easy range (reading range minus its top 4 semitones) | as standard, and fewer key changes (key-plan penalty 1.0) |

`Composition.transposed(n)` and `keys.semitones_to(key, "Bb" | "Am" | "-2:minor")` move a piece to a
concert key; the arranger then places every part in range as usual.

## Confidence and review marks

`confidence.py`: a solo note's `confidence` is the probability that it is right (pitch and onset
match the score). Logistic regression over:

| Input | Meaning |
|---|---|
| `mus`, `bp`, `mus_bp` | MuScriptor / Basic Pitch also found the note (SwiftF0 always did). A Basic Pitch file standing in for MuScriptor counts once |
| `log_dur` | log of the note length in seconds (≥ 0.02) |
| `support` | mean SwiftF0 voicing confidence over the note's first 0.3 s, over frames within 1 semitone (octave-folded) of its pitch, else 0 |
| `no_contour` | 1 when there is no contour (then `support` = 0) |
| `separated` | 1 when the solo was separated from a mix (a stem), 0 when recorded alone |
| `sep_support`, `sep_voted` | `separated` × `support`, `separated` × (`mus` or `bp`) |

`calibration.json` holds the weights, the clamping `ranges` (`log_dur`, `support` and `sep_support`
are clamped into them before scoring), `mark_risk` and `very_risk`. `eval/brasscribe_eval/confidence_bench.py`
fits it on notes with ground truth and checks it on held-out recordings.

A note is **marked** when `1 - confidence >= mark_risk` and **very unsure** when `>= very_risk`.
Marked notes of one voice form one review group when at most one unmarked note lies between
them, no rest of a beat or more separates them, and the group spans at most two bars. Each
group gets one "?" (boxed when any member is very unsure) at its first note, that note is
coloured, and a dashed bracket spans groups of more than one note.
