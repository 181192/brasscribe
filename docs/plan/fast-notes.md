# Fast notes and two-note alternations

The owner says: "On the melody parsing, we are not doing a good job on fast tones or when we are interleaving
between two tones, that is often used on cornet/trumpet." This plan covers two kinds of material:

- fast passages: semiquavers and faster, and double or triple tonguing;
- rapid alternation between two notes: lip trills, shakes, trills, and tremolo between two pitches.

Status: measurement and diagnosis are done. The fixes wait for review. An independent baseline is in
[research/17-fast-notes-critique.md](../research/17-fast-notes-critique.md) (branch `review/fastnotes-critic`).
Where both measured the same thing, the numbers below agree with it.

## Short answer

Fast notes are lost at four points in the solo path, and they compound. Fixing any one of them alone gains
little. Fixing three of them together, as a crude ablation, more than doubles what reaches the score:

| Figure recall in the written score | today | segmentation hold 40 ms, line 30 ms, collision-aware grid |
|---|---|---|
| synthetic, real trumpet samples, oracle beats | 0.34 | 0.77 |
| synthetic, real trumpet samples, Beat This! small0 | 0.29 | 0.68 |
| synthetic, all renders (samples, hall, SoundFont), small0 | 0.22 | 0.53 |
| URMP trumpet parts: notes under 160 ms apart, small0 | 0.26 | 0.52 |
| URMP trumpet parts: every note, note F1 | 0.817 | 0.838 |
| ChoraleBricks solo stems (slow legato): note F1 | 0.710 | 0.704 |

That ablation also makes false notes on the must-stay-one-note controls: scoop extras go from 0.62 to 2.56 per
note, and vibrato from 0 to 0.13. So the shipped fix has to take a different route at the segmentation step.

Losses by stage (real trumpet samples, figure notes, small0 beats unless noted):

1. **Segmentation** (SwiftF0 `segment_notes`, hold 80 ms).
   - The contour holds 0.97 of the figure notes. SwiftF0's notes keep 0.62.
   - Slurred alternation at 9–12 notes/s keeps 0.20, and above 12/s keeps 0.04.
   - Repeated tongued notes on one pitch keep 0.45. Pitch alone cannot split them.
2. **Line extraction** (`line()`: 60 ms minimum, 50 ms merge; `lines.rs` in Rust).
   - Tongued alternation at 9–12/s drops from 0.54 to 0.29.
3. **Quantization** (`GRIDS` penalties with no 32nds, then `_monophonize` drops notes that share a tick).
   - The reference notes themselves, quantized on the same grid, keep only 0.49 with oracle beats.
   - The line drops from 0.47 to 0.29.
   - Runs faster than 12/s keep 0.01 even with perfect onsets.
4. **Beats.** With oracle beats instead of small0, the written score keeps 0.34 instead of 0.29. On slow 16th
   runs the gap is 0.84 against 0.44.

What costs nothing:

- **The tracker's frame rate.** The contour holds 0.97 of the figure notes on dry samples and 0.92 in the hall.
  Only above 12 notes/s does it slip, to 0.68–0.86.
- **Free time.** Synthetic clips have steady tempo, so free time plays no part there. URMP: 0.258 against 0.262.
- **The arranged lead part at faithful.** It is identical to the written solo line.

Standard and easier drop more notes by design (`merge_sixteenths`). That is simplification, not loss, and a trill
mark is the readable way to keep an alternation there.

**Separation** (Mega-53 on the solo plus a band bed 12 dB under it) costs little on the whole, but it hits
slurred alternation hard:
- On 10 clips: contour 1.00 → 0.94, SwiftF0 0.75 → 0.64, written 0.45 → 0.38.
- Slurred alternation at ≤ 8/s: SwiftF0 0.48 → 0.05.
- Vibrato gains 0.25 extras per note. See §2.2.

## 1. The eval set

Code: `eval/brasscribe_eval/fast_notes.py` builds the set, and `fast_notes_bench.py` measures it. Clips are in
`data/eval/fast-notes*/`. Nothing goes into `data/golden`.

| Set | Clips | Ground truth | Licence |
|---|---|---|---|
| synthetic `samples` | 135 | exact (performed onsets) | University of Iowa MIS sustains, VSCO 2 CE staccato |
| synthetic `room` | 36 | exact | as above, plus an OpenAIR church impulse response (St Margaret's, York) |
| synthetic `sf2` | 135 | exact (MIDI) | the band SoundFont's Solo Cornet through FluidSynth |
| separated (`sep`) | 10 | exact | `samples` plus a band bed, run through Mega-53 |
| URMP trumpet parts | 21 | URMP note annotations | local only |
| ChoraleBricks solo stems | 93 | ChoraleBricks annotations | the frozen CI fixtures (CC-BY 4.0) |
| Mikkel | 1 | none: proxy counts | test only, never bundled |

**Synthetic clips.** Each clip is four bars of 4/4:
- a bar of tongued quarters;
- two bars of the figure under test;
- a closing half note.

The figures:
- alternation at m2, M2, m3, P4 and the octave (a lip slur, C4–C5);
- a diatonic run;
- an arpeggio;
- one pitch re-tongued (double or triple tonguing).

Each figure is played:
- at 4, 6 and 8 notes per beat, which is 6–20 notes/s;
- at 90, 120 and 150 BPM;
- slurred or tongued.

Slurred means no re-attack: the samples renderer crossfades the steady parts over 12 ms with a small level dip at
each change. That makes the pitch change the only onset. Each onset carries a few milliseconds of performer
jitter.

**Controls.** Every note in these must stay one note:
- vibrato: ±60 c at 5.5 Hz;
- scoop: up from 200 c flat over 120 ms;
- fall: down 400 c over the last 250 ms;
- slow two-note slurs at m2, M2 and the octave.

The critic adds 35 real Iowa vibrato sustains, dry and in a hall (`research/fastnotes/real_vibrato.py`). The
gate: no increase in extra notes, and no trill mark.

**Trackers.** SwiftF0 notes and contour, Basic Pitch, and Beat This! small0 are run once per clip, in batches,
in the adapters' own environments. Basic Pitch stands in for MuScriptor, as on the phone and in
`solo_instruments_bench`.

**CI.** The tracker outputs of the `samples` and `room` clips will be frozen to `eval/fixtures/fast-notes/`, like
`choralebricks-solo`, as a new `fast-notes` bench suite with baselines.

**Stages scored.** Every clip goes through the real solo path: `arrange_layers_song`, lineup minimal, no seat.
`build()` now takes an optional `trace` dict. The stages:

| Stage | What it is |
|---|---|
| `contour` | the SwiftF0 frame contour holds the note's pitch for half of its middle frames |
| `sw`, `bp` | tracker notes |
| `line` | SwiftF0-anchored consensus, `line()`, contour note ends |
| `q_ref` | the *reference* notes quantized on the same grid: the quantizer's loss on its own |
| `quantized` | the line after `quantize()` |
| `written` | the Composition's solo voice |
| `lead:<difficulty>` | the arranged lead part |

Ticks are mapped back to seconds through the beat grid, so a note written in the wrong slot counts as wrong.

**Metrics.** Notes are matched one to one. The window is 50 ms, or half the gap to the nearest neighbour when that
is smaller.
- `fig_recall`: recall of the figure notes.
- `note_f1` and `onset_f1`, and `onset25_f1` at 25 ms.
- `alt_kept`: alternation clips whose figure keeps at least 80 % of its notes on the right pitches.
- `upper_share`: which note survives an alternation.
- `extra`: control clips, extra notes per reference note.

```
python -m brasscribe_eval.fast_notes build|track|urmp|chorales|separate
python -m brasscribe_eval.fast_notes_bench --root data/eval/fast-notes [--beats oracle,small0]
python -m brasscribe_eval.fast_notes_bench --root … --ablate today,hold40,line30,grid-collide,…
python -m brasscribe_eval.fast_notes_bench --mikkel --ablate today,…
```

## 2. Where the notes are lost

### 2.1 Waterfall

Synthetic figure recall at each stage. Rates are notes per second.

**Oracle beats:**

| Group | contour | sw | bp | line | q_ref | quantized | written | lead faithful | lead easier |
|---|---|---|---|---|---|---|---|---|---|
| all | 0.86 | 0.42 | 0.64 | 0.36 | 0.45 | 0.26 | 0.26 | 0.26 | 0.18 |
| samples | 0.97 | 0.63 | 0.60 | 0.47 | 0.49 | 0.34 | 0.34 | 0.34 | 0.24 |
| room | 0.92 | 0.43 | 0.65 | 0.32 | 0.38 | 0.23 | 0.23 | 0.23 | 0.10 |
| sf2 | 0.74 | 0.22 | 0.68 | 0.27 | 0.43 | 0.19 | 0.19 | 0.19 | 0.14 |
| alt slurred ≤ 8/s | 0.93 | 0.50 | 0.87 | 0.56 | 1.00 | 0.54 | 0.54 | 0.54 | 0.35 |
| alt slurred 9–12/s | 0.81 | 0.20 | 0.83 | 0.20 | 0.33 | 0.12 | 0.12 | 0.12 | 0.08 |
| alt slurred > 12/s | 0.68 | 0.04 | 0.45 | 0.04 | 0.05 | 0.03 | 0.03 | 0.03 | 0.03 |
| alt tongued 9–12/s | 0.91 | 0.54 | 0.81 | 0.29 | 0.46 | 0.16 | 0.16 | 0.16 | 0.13 |
| run slurred 9–12/s | 0.91 | 0.57 | 0.58 | 0.65 | 0.53 | 0.35 | 0.35 | 0.35 | 0.19 |
| run slurred > 12/s | 0.86 | 0.31 | 0.24 | 0.29 | 0.01 | 0.09 | 0.09 | 0.09 | 0.05 |
| run tongued 9–12/s | 0.98 | 0.75 | 0.25 | 0.56 | 0.55 | 0.35 | 0.35 | 0.35 | 0.20 |
| repeat tongued 9–12/s | 1.00 | 0.45 | 0.49 | 0.24 | 0.59 | 0.18 | 0.18 | 0.18 | 0.18 |

**Beat This! small0 beats:**

| Group | contour | sw | bp | line | q_ref | quantized | written | lead faithful | lead easier |
|---|---|---|---|---|---|---|---|---|---|
| all | 0.86 | 0.42 | 0.64 | 0.36 | 0.32 | 0.22 | 0.22 | 0.22 | 0.14 |
| samples | 0.97 | 0.62 | 0.60 | 0.47 | 0.40 | 0.29 | 0.29 | 0.29 | 0.21 |
| run slurred ≤ 8/s | 0.99 | 0.74 | 0.91 | 0.89 | 0.49 | 0.44 | 0.44 | 0.44 | 0.29 |
| run tongued ≤ 8/s | 0.99 | 0.99 | 0.78 | 0.99 | 0.56 | 0.50 | 0.50 | 0.50 | 0.29 |

**Alternations kept** (at least 80 % of the figure, on the right pitches), oracle beats:

| Group | sw | bp | line | written |
|---|---|---|---|---|
| slurred ≤ 8/s | 0.40 | 0.76 | 0.48 | 0.48 |
| slurred 9–12/s | 0.13 | 0.73 | 0.13 | 0.02 |
| slurred > 12/s | 0 | 0 | 0 | 0 |
| tongued 9–12/s | 0.42 | 0.67 | 0.11 | 0.00 |

After `line()`, 81–100 % of what remains of a collapsed alternation is the upper note. Both `line()` and
`_monophonize` keep the higher pitch.

**Controls,** extra notes per reference note (oracle beats):

| Control | sw | bp | line | written |
|---|---|---|---|---|
| vibrato | 0 | 4.69 | 0 | 0 |
| scoop | 0.88 | 1.06 | 1.56 | 0.62 |
| fall | 2.00 | 1.06 | 2.06 | 1.50 |
| slow slur | 0.79 | 0.33 | 0.75 | 0.46 |

Today already writes false notes on falls and scoops. The gate for the fix is "no increase".

**URMP trumpet** (21 parts, small0, fast = notes under 160 ms from a neighbour):

| Metric | contour | sw | bp | line | q_ref | quantized | written | lead easier |
|---|---|---|---|---|---|---|---|---|
| fast-note recall | 0.87 | 0.58 | 0.56 | 0.58 | 0.28 | 0.26 | 0.26 | 0.18 |
| note F1, all notes | | 0.96 | 0.83 | 0.94 | 0.83 | 0.82 | 0.82 | 0.68 |

On real playing, the quantizer is the largest loss: even perfect onsets keep only 0.28 of the fast notes.

**Mikkel** has no ground truth, so these are proxy counts, not F1. "Fast passages" are runs of at least four
contour plateaus, each at least 48 ms and within ±35 c of a semitone, starting less than 160 ms apart. The
contour's own plateaus overcount, because vibrato and bends break into pieces.

|  | plateaus | sw | line | quantized, written |
|---|---|---|---|---|
| in fast passages | 887 | 667 | 658 | 535 |
| whole solo | 1087 | 837 | 827 | 694 |

With the ablation above, the fast passages get 842 written notes. The Mikkel golden will change.

### 2.2 Separation

Ten `samples` clips were mixed with a band bed and separated by Mega-53. The bed is sustained chords from the
band SoundFont, 12 dB under the solo. The trumpet stem was then tracked like any clip (`fast_notes separate`).
Figure recall, oracle beats:

| Clips | contour | sw | bp | line | quantized, written |
|---|---|---|---|---|---|
| the 8 figure clips, dry | 1.00 | 0.75 | 0.65 | 0.55 | 0.45 |
| the same, separated | 0.94 | 0.64 | 0.63 | 0.48 | 0.38 |
| alt slurred ≤ 8/s (2 clips), dry | 1.00 | 0.48 | 0.63 | 0.45 | 0.42 |
| the same, separated | 0.77 | 0.05 | 0.48 | 0.05 | 0.02 |

**Controls, separated:**
- vibrato: 0.25 extra notes per note (dry: 0);
- scoop: 0.25 (dry: 0.50).

**What this means:**
- Separation smears the pitch changes of a slur, and adds a little pitch noise to sustained notes.
- F1's plateau test has to hold on separated stems, not just on dry audio.
- The separated clips are part of its gate.

### 2.3 Candidates, one by one

The evidence comes from the waterfall, the one-knob ablations and the code.

| Candidate | Verdict | Evidence |
|---|---|---|
| Tracker frame rate or hop (16 ms), smoothing | not the problem below 12 notes/s | The contour holds 0.97 of the figure notes (samples), 0.92 (hall). Above 12/s it holds 0.68–0.86, a real ceiling. |
| Median filters | none in the solo path | |
| Segmentation hold, `pitch_hold_ms=80` | **major** | β = 5 frames per note. A return to the previous pitch pays twice, so a semitone trill collapses (sw 0.20 at 9–12/s slurred). Hold 40 gives 0.30 written, but scoop extras go from 0.62 to 0.88. Hold 20 gives 0.35, but vibrato goes to 5.25 extra per note. A global hold change is out. |
| Minimum note duration (`line()` 60 ms) and 50 ms merge | **major above 9/s**, combined with the grid | Alone: +0.02. Combined with the others it is needed: a 32nd at 150 BPM is 50 ms. |
| Merging same or adjacent pitches | **yes**, at two places | `line()` merges onsets under 50 ms apart, and `_monophonize` merges notes sharing a tick. Both keep the higher pitch (upper-share 0.8–1.0). |
| Onsets on legato slurs (no re-articulation) | **the core of the alternation loss** | Slurred alternation 9–12/s: contour 0.81, sw 0.20. Tongued: sw 0.54. Basic Pitch hears the slurred changes (0.83), but the line keeps only clusters with SwiftF0. |
| Repeated notes on one pitch | **major** (sw 0.45 at 9–12/s) | No pitch change, so segmentation needs the level dip of the tongue. |
| Quantization grid too coarse | **major** | `q_ref` 0.49 with oracle beats. There is no 32nd grid. Per-note penalties make 8ths beat triplets (critic §2). `_monophonize` drops collisions silently. Collision-aware grid alone: 0.34 → 0.42 (samples, oracle). |
| Tempo or beat errors | **moderate** | Oracle against small0: 0.34 against 0.29 overall, 0.84 against 0.44 on slow 16th runs. The collision-aware grid recovers most of that: small0 run slurred ≤ 8/s goes 0.44 → 0.72. |
| Free time (`FREE_GRIDS` 1, 2) | not in these sets; real in cadenzas | Critic §2: 16ths keep 13/24 in free time. It matters on Mikkel's intro, so it is in F3. |
| Source separation smearing | **moderate, on slurred alternation** | See §2.2. |
| Difficulty (standard, easier) | by design | `merge_sixteenths` halves 16ths. A trill mark is the readable form there (F5). |

### 2.4 Ablations

Figure recall at the written stage. `grid` is the collision-aware grid: 32nds allowed, and a grid that puts two
onsets of one beat on one slot pays per lost note.

| Group | today | hold 40 | hold 20 | line 30 ms | grid | no free time | hold 40 + line 30 + grid |
|---|---|---|---|---|---|---|---|
| samples, oracle | 0.34 | 0.41 | 0.41 | 0.37 | 0.42 | 0.34 | 0.77 |
| samples, small0 | 0.29 | 0.34 | 0.35 | 0.32 | 0.38 | 0.30 | 0.68 |
| alt slurred 9–12/s, oracle | 0.12 | 0.30 | 0.36 | 0.12 | 0.18 | 0.12 | 0.52 |
| run slurred > 12/s, oracle | 0.09 | 0.12 | 0.12 | 0.12 | 0.23 | 0.09 | 0.67 |
| URMP fast notes, small0 | 0.26 | 0.32 | | 0.26 | 0.38 | 0.26 | 0.52 |
| scoop extras, oracle | 0.62 | 0.88 | 0.94 | 0.62 | 0.62 | 0.62 | **2.56** |
| vibrato extras, oracle | 0 | 0 | **5.25** | 0 | 0 | 0 | **0.13** |
| chorales, note F1, small0 | 0.710 | 0.712 | | 0.710 | 0.709 | | 0.704 |

## 3. Fixes, by layer

Every fix lives in `music/` (Python) and the Rust core, with conformance cases for each. SwiftF0's
`segment_notes` and its Swift and Kotlin ports stay as they are. The new step reads the contour, which already
reaches the core on every platform (`Layers.solo_contour`). So:
- the cached SwiftF0 outputs and the `choralebricks-solo` and `contours` fixtures keep their fingerprints;
- the on-device path gets the fix through the core.

**F1. Contour onsets for the solo line** (new `brasscribe_music/onsets.py`, `core/.../onsets.rs`). This runs
before `cluster()`, on the SwiftF0 notes, when a contour is present. It splits a note in two cases:
- **Pitch change.** The contour holds another semitone for at least 3 frames (48 ms). "Holds" means within
  ±35 c on the piece's own tuning, which is the circular mean of the confident frames, as in doc 11.
- **Articulation.** The same pitch is re-tongued: a loudness dip of at least 6 dB between two peaks at least
  50 ms apart.

What it must not split:
- **Vibrato** never reaches 65 c from its note within ±35 c of the next semitone.
- **Scoops and falls** are monotonic glides at a note's start or end. A plateau there must last at least 80 ms,
  a real note, before it splits.
- **Alternation.** Plateaus that alternate between two semitones (A B A …) split at 3 frames. They are
  unambiguous, and they are where the hold loses notes today.

The new notes stay sourced `sw`, so Basic Pitch can still confirm them in `cluster()`. The O(frames) scan runs
once per note, with no FFT.

Alternative rejected: a global hold change. §2.4 shows the vibrato and scoop cost.

Optional F1b: let a Basic Pitch note without SwiftF0 into the line when the contour supports it (at least 60 % of
its frames on its pitch). Basic Pitch hears slurred alternation better (0.83 against 0.20). Decide on the
numbers after F1.

**F2. Line thresholds for the solo line.** Minimum 30 ms instead of 60 ms, and merge window 20 ms instead of
50 ms. This is a parameter of the solo call only. Bass and orchestra keep their defaults.

**F3. Collision-aware quantization** (`quantize.py` / `quantize.rs`).
- Per beat, a grid pays for every onset that would share a slot with another. Onsets just before the next beat
  count against it too.
- Grid 8 (32nds) joins the set, at a penalty above 6.
- Inside free time, `FREE_GRIDS` stay, unless they collide. Then the full set is allowed.
- `choose_level` is left alone, so a doubled grid is not counted twice.
- Beats with no collision choose exactly as today. That keeps slow, chorale and golden churn to the passages
  that change.
- Collisions that remain after that are shifted to the next free slot at the finest grid, instead of dropped
  by `_monophonize`. The note is marked uncertain.

The unit fixtures (`core/brasscribe-core/tests/fixtures/quantize.json`) are regenerated on purpose.

**F4. Uncertainty, not deletion.**
- Split notes that only SwiftF0 found get their confidence from the existing calibrated model: length, contour
  support, agreement. Short and unconfirmed notes get "?" review marks. They are never dropped for low
  confidence.
- Report the "?" rate on correct and wrong fast notes (`q_false_alarm`, `q_hit`). Refit only if it is badly off.

**F5. Alternation as a trill (optional, last).** A sustained two-pitch alternation is:
- at least 6 changes;
- faster than the written grid can hold, or with difficulty at standard or easier.

It is written as one note on the lower (main) pitch, spanning the alternation:
- 1–2 semitones: `tr` plus a wavy line, with an accidental above for the upper note when it is not in the key;
- 3 semitones or more: a shake, or "lip trill" text for an octave.

At faithful, a figure that fits 16ths or sextuplets stays written out.

The consumers:
- the Composition JSON (`Note` ornament field), the Rust model and `pyjson`;
- the MusicXML writers on both sides, the talking score and braille;
- the MuseScore round trip;
- the apps' decoders, which must ignore the field. Playback plays the main note, and that is documented.

Scope risk is high. The step goes in only after F1–F4 land, and only if the critic agrees.

## 4. Gates (before → after)

| Gate | Before | Target |
|---|---|---|
| Figure recall, written, samples, oracle / small0 | 0.34 / 0.29 | ≥ 0.70 / ≥ 0.60 |
| Figure recall, written, all synthetic, small0 | 0.22 | ≥ 0.45 |
| Alternations kept, written, slurred 9–12/s (oracle) | 0.02 | ≥ 0.60 |
| URMP fast-note recall / note F1 (small0) | 0.26 / 0.817 | ≥ 0.45 / ≥ 0.815 |
| Control extras (vibrato, scoop, fall, slow slur), written | 0 / 0.62 / 1.50 / 0.46 | no increase |
| Critic's real vibrato set: extras, trill marks | 0.14 dry / 0.40 hall, 0 | no increase, 0 |
| Chorale solo stems, written note F1 (small0) | 0.710 (trumpet 0.904) | ≥ 0.705 (trumpet ≥ 0.899) |
| `brasscribe bench cpu` | 19 pass, 1 pre-existing fail\* | no new failure |
| Mikkel golden | — | the diff explained, in a sibling directory |

\* `solo-ondevice.part_files_identical_frac` is 0.125 against 1.000 at base 9e59634c, before any change.

Numbers are reported per stage before and after, in this file.

## 5. Goldens and parity

- **Mikkel.** The golden `data/golden/mikkel-arranged-band` changes, because its solo has fast passages. The
  new golden goes into `data/golden/mikkel-arranged-band.fast-notes`, and every pointer is repointed:
  - `core/conformance/.../cases.py` `MIKKEL_GOLDEN`;
  - the engine's golden checks;
  - the bench's `mikkel-golden` suite;
  - the docs;
  - the app tests that read the golden: Android (`BandEstimateTest`, `PartsAndAnnouncementsTest` and three
    Gradle modules), Apple (PlaybackKit, ScoreKit, TranscriptionKit and NotationKit tests), and Windows
    (`TestPaths.cs`). `git grep mikkel-arranged-band` lists 30 files.

  Tests that pin counts from the golden move with it, and the fast tier runs on every area touched.

  `data/golden` is never modified in place. The coordinator promotes it at merge.
- **Entertainer.** The case's golden (`data/runs/apple/entertainer-ref/layered`) gets the same treatment if the
  output changes.
- **Rust parity.** `onsets.rs`, the `line` parameters and `quantize.rs` mirror Python exactly. New unit
  fixtures: onsets on seeded synthetic contours, including the traps, and quantize collision cases. A new
  conformance case runs the fast-notes clips through `layers`.
- **Devices.** The Kotlin and Swift segmenters are unchanged. The core does the new work. Time the added scan on
  a long contour, since the S25 is available.

## 6. Order of work

After review, each step goes to the critic when it is done:
1. The harness and fixtures: this commit, plus the frozen `fast-notes` suite.
2. F3, quantization (independent of audio).
3. F2 + F1, the line and contour onsets.
4. F4, uncertainty.
5. Goldens, full check, and the before/after numbers.
6. F5, the trill, if agreed.
