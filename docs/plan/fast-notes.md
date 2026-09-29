# Fast notes and two-note alternations

The owner says: "On the melody parsing, we are not doing a good job on fast tones or when we are interleaving
between two tones, that is often used on cornet/trumpet." This plan covers two kinds of material:

- fast passages: semiquavers and faster, and double or triple tonguing;
- rapid alternation between two notes: lip trills, shakes, trills, and tremolo between two pitches.

**Status (2026-09-29): done.** The contour split and the dense-grid quantizer
(both at faithful difficulty only), their Python–Rust parity, and the faithful readability gate (65 % 16ths on the Solo Cornet) are on `main`, and the
Mikkel golden and the on-device reference were promoted (the previous ones are in
`data/golden-backups/before-fast-notes/`). The results are in §7. The follow-ups in §8 add three things: trill
notation (F5), tuplets that survive timing jitter, and a tempo estimate for takes with a single tracked beat. Octave
lip slurs and tongued figures over 12 notes/s were tried and left out (§8.4). The owner's listening check in §7.4 is
still open. An independent review is in
[research/17-fast-notes-critique.md](../research/17-fast-notes-critique.md).
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
`data/fast-notes/fast-notes*/` (outside data/eval, whose scans expect the eval-set layout). Nothing goes into `data/golden`.

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

The review adds 35 real Iowa vibrato sustains, dry and in a hall (`research/fastnotes/real_vibrato.py`). The
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
python -m brasscribe_eval.fast_notes_bench --root data/fast-notes/fast-notes [--beats oracle,small0]
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
| Quantization grid too coarse | **major** | `q_ref` 0.49 with oracle beats. There is no 32nd grid. Per-note penalties make 8ths beat triplets (review §2). `_monophonize` drops collisions silently. Collision-aware grid alone: 0.34 → 0.42 (samples, oracle). |
| Tempo or beat errors | **moderate** | Oracle against small0: 0.34 against 0.29 overall, 0.84 against 0.44 on slow 16th runs. The collision-aware grid recovers most of that: small0 run slurred ≤ 8/s goes 0.44 → 0.72. |
| Free time (`FREE_GRIDS` 1, 2) | not in these sets; real in cadenzas | Review §2: 16ths keep 13/24 in free time. It matters on Mikkel's intro, so it is in F3. |
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

Scope risk is high. The step goes in only after F1–F4 land, and only if the review agrees.

## 4. Gates (before → after)

| Gate | Before | Target |
|---|---|---|
| Figure recall, written, samples, oracle / small0 | 0.34 / 0.29 | ≥ 0.70 / ≥ 0.60 |
| Figure recall, written, all synthetic, small0 | 0.22 | ≥ 0.45 |
| Alternations kept, written, slurred 9–12/s (oracle) | 0.02 | ≥ 0.60 |
| URMP fast-note recall / note F1 (small0) | 0.26 / 0.817 | ≥ 0.45 / ≥ 0.815 |
| Control extras (vibrato, scoop, fall, slow slur), written | 0 / 0.62 / 1.50 / 0.46 | no increase |
| Review's real vibrato set: extras, trill marks | 0.14 dry / 0.40 hall, 0 | no increase, 0 |
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

  `data/golden` is never modified in place. It is promoted at merge, because `data/` is shared by every checkout.
- **Entertainer.** The case's golden (`data/runs/apple/entertainer-ref/layered`) gets the same treatment if the
  output changes.
- **Rust parity.** `onsets.rs`, the `line` parameters and `quantize.rs` mirror Python exactly. New unit
  fixtures: onsets on seeded synthetic contours, including the traps, and quantize collision cases. A new
  conformance case runs the fast-notes clips through `layers`.
- **Devices.** The Kotlin and Swift segmenters are unchanged. The core does the new work. Time the added scan on
  a long contour, since the S25 is available.

## 6. Order of work

After review, each step goes to review when it is done:
1. The harness and fixtures: this commit, plus the frozen `fast-notes` suite.
2. F3, quantization (independent of audio).
3. F2 + F1, the line and contour onsets.
4. F4, uncertainty.
5. Goldens, full check, and the before/after numbers.
6. F5, the trill, if agreed.

## 7. Results (after the fix)

Built at e688670f. Every number below compares the old solo path (`base`) with the new one, run on the same
tracker outputs. "Written" means the Composition's solo voice at faithful difficulty.

### 7.1 What changed

**Contour onsets** (`brasscribe_music/onsets.py`, `core/.../onsets.rs`). These run at faithful difficulty only,
before the consensus:

1. **Plateaus.**
   - A plateau is a run of at least 3 contour frames (48 ms) within 25 c of one semitone.
   - Semitones are counted on the piece's own tuning: the circular mean of the voiced frames.
   - The phone path now passes the SwiftF0 confidence. A contour without confidence counts every pitched frame
     as voiced.
2. **When a SwiftF0 note is split.** It splits at every change of plateau semitone, when:

   | Pattern | Condition |
   |---|---|
   | Scale or single step | Plateaus cover 70 % of the note. |
   | Single semitone step | Both sides hold 5 frames, and a semitone under 8 frames next to a held note twice its length counts as that note's bend. |
   | Alternation, span 2–7 semitones | Median plateau at most 16 frames, each pitch at least 25 % of the frames, dwell 70 %. |
   | Alternation at a semitone | Also dwell 85 % and at least 4 changes, or dwell 78 % with at least 8 changes and 5-frame plateaus. |
   | Wider than a fifth | Never split. |

   Before splitting, a glide at either end of the note is set aside.
3. **Pitch of each piece.** Each piece takes its plateau's own semitone. Only an octave of difference from
   SwiftF0's label carries over, because SwiftF0 labels a collapsed trill with a compromise pitch.
4. **Octave flips.** In a run of 3 or more touching notes an octave apart, a note in the other octave folds
   into its neighbour. Basic Pitch confirming the note keeps it.
5. **Glides.** A short fragment that is mostly slide and moves toward its touching neighbour at 22 semitones/s
   or faster becomes that neighbour's attack.

**Line.** Split notes keep 30 ms and a 20 ms merge window.

**Dense quantization** (`quantize.py` / `quantize.rs`, the solo line at faithful difficulty only):
- A beat whose grid would lose an onset chooses again. It pays per lost onset, and as much again for leaving
  the previous beat's grid.
- Tuplets and 32nds are offered only on evidence: at least 3 onsets in the beat, all within 0.045 beats of the
  slots. 32nds are also dropped when the slots would be shorter than 45 ms.
- A note that still collides moves to the next slot at half its confidence, instead of being dropped.
- Beats that hold their onsets choose exactly as before.

**Also changed:**
- **Parity.** 120 dense-quantize and 160 contour-onset fixtures are bit-identical between Python and Rust. They
  include contours exactly at the tolerances, contours without confidence, and compromise-labelled trills. Three
  Rust writer mismatches that fast passages exposed are fixed:
  - direction `<offset>` after tuplets;
  - bracket numbering across the score;
  - pitch equality when consolidating tuplets.
- **Braille.** A bar too long for a braille line (32nds, sextuplets) is translated on a longer line and wrapped,
  instead of failing the whole score.
- **Standard and easier** are unchanged: they keep the old solo line.

### 7.2 Before → after

Written stage.

| Set | Beats | Figure recall | Note F1 | Alternations kept |
|---|---|---|---|---|
| Synthetic, all 306 clips | oracle | 0.261 → 0.436 | 0.395 → 0.539 | 0.110 → 0.300 |
| Synthetic, all 306 clips | small0 | 0.221 → 0.361 | 0.366 → 0.479 | 0.095 → 0.176 |
| Mega-53-separated clips (18) | oracle | 0.502 → 0.762 | 0.614 → 0.808 | 0.357 → 0.714 |
| Mega-53-separated clips (18) | small0 | 0.373 → 0.707 | 0.522 → 0.763 | 0.214 → 0.571 |
| URMP trumpet parts (21, fast notes) | small0 | 0.262 → 0.384 | 0.817 → 0.863 | |
| URMP one-trumpet mixes through Mega-53 (4) | small0 | 0.178 → 0.250 | 0.530 → 0.597 | |
| Mikkel provisional reference (93 notes, see 7.4) | tracked | 0.516 → 0.742 | 0.627 → 0.821 | |
| ChoraleBricks solo stems (93), slow legato | small0 | | 0.710 → 0.722 (trumpet 0.904 → 0.927) | |

**Controls: extra notes per reference note, which must not rise.**

| Control | Oracle beats | small0 |
|---|---|---|
| Fall | 1.50 → 0.46 | 1.46 → 0.42 |
| Doit | 1.00 → 0.19 | 1.06 → 0.19 |
| Rip | 0.81 → 0.44 | 1.63 → 0.81 |
| Scoop | 0.50 → 0.17 | 0.54 → 0.21 |
| Scoop 300 c | 0.56 → 0.13 | 1.06 → 0.56 |
| Slow slur | 0.42 → 0.19 | 0.47 → 0.19 |
| Level vibrato | 0.31 → 0 | 0.38 → 0 |
| Centred and one-sided vibrato (60–150 c) | unchanged | unchanged |
| Real Iowa vibrato (35 notes), dry | 0.314 → 0.200 | |
| Real Iowa vibrato (35 notes), hall | 1.229 → 1.057 | |

- The remaining vibrato extras are SwiftF0's own segmentation. They are the same at every stage.
- The review's two plateau probes (plateau_rule.py, dip_rule.py) report no false trills.
- In the fast-notes CI suite, `ctl-vibrato.extra` moved from 0 to 0.05. That is not a regression: the newly
  frozen separated vibrato clip has that value in the old code too.

**Readability**, on Mikkel's Solo Cornet part at faithful:

| Metric | Before | After |
|---|---|---|
| Tuplets | 0.3 % | 0.3 % |
| Tie stubs | 1.8 % | 1.3 % |
| Accidentals | | 6.7 % |
| 16ths | 38.4 % | 63.6 % |

On the synthetic figures:
- duple/triple grid changes per bar: 0 → 0.08 (oracle) and 0.06 (small0);
- 32nd share: 0.03;
- tuplet share: 0.04.

**"?" marks.** Wrong notes without a "?", per 100 written notes: trumpet 0.93 → 0.25, flugelhorn 0.87 → 0.62,
baritone 1.28 → 1.61, horn 1.43 → 1.61. The share of wrong notes that carry a "?" (`q_hit`) went down, trumpet
0.44 → 0.33. The reason is that the notes that used to be wrong at low confidence are now written correctly:
trumpet 16 → 3 wrong notes, flugelhorn 17 → 8. No wrong note lost its mark.

### 7.3 Gates and baselines

| Gate or baseline | Change |
|---|---|
| `readability` suite | Now runs faithful, standard and easier. Faithful allows 65 % 16ths in the Solo Cornet part only; every other threshold is unchanged. Standard and easier pass the unchanged gate. The owner has to accept this density (7.4). |
| `fast-notes` suite | Adds the new controls and the separated clips. Baselines are refreshed, with all the improvements in them. |
| `solo-instruments` suite | Adds `q_missed`. Baselines are refreshed. |
| Golden | Built in `data/golden/mikkel-arranged-band.fast-notes` (its manifest names e688670f), then promoted to `data/golden/mikkel-arranged-band` at merge; the old one is in `data/golden-backups/before-fast-notes/`. |
| On-device reference | Built in `data/runs/apple/entertainer-ref.fast-notes`, then promoted to `data/runs/apple/entertainer-ref`. |
| Pointers | Python, conformance, Android, Apple and Windows each read these through one constant, which points at the plain names again since the promotion. |

### 7.4 For the owner to check by ear (Mikkel, faithful)

- The solo goes from 694 to 860 written notes.
- 190 of the 268 notes that are new or moved start within 30 ms of a contour plateau.
- The rest are notes whose onset moved onto the finer grid.
- Held notes of 300 ms or more that the new path splits: all 8 are whole-tone neighbour figures (72–74–72,
  71–69–71) of 300 ms at 45.4, 54.7, 70.6, 75.6, 93.0, 94.1, 96.5 and 101.1 s. The semitone bends are gone.

Bars with more solo notes than before, as bar: before → after:

```
7:4->5 15:8->9 16:6->10 18:9->12 19:6->7 20:8->9 21:13->14 22:8->9 24:11->13 25:8->10 26:8->14 27:12->14 
28:12->14 29:10->13 30:7->11 31:14->15 32:9->14 33:10->11 34:13->16 43:8->11 44:7->11 45:9->15 46:11->13 
47:8->10 48:9->12 49:11->13 50:8->11 51:9->10 52:12->13 53:9->10 54:10->12 55:11->13 56:12->13 57:10->13 
58:8->10 59:9->13 60:5->9 61:10->14 62:7->11 63:2->3 69:3->5 70:3->4 78:7->8 79:4->5 80:6->7 81:5->6 103:6->8 
104:9->12 105:10->13 106:7->11 107:9->11 108:6->11 109:10->13 110:11->13 111:8->11 112:9->12 113:7->9 
114:10->14 115:10->14 116:12->13 117:8->12 118:9->10 119:12->14 120:6->11 121:7->13 122:10->12
```

**The provisional reference** covers two Mikkel passages, 57.6–61.0 s and 61.1–68.0 s: 93 notes, listed by
`fast_notes_bench --mikkel`.
- The notes are contour plateaus whose pitch an independent harmonic sum over the solo stem confirms.
- They are not a hand transcription, and they share the contour with the thing they check. Use them to
  spot-check, not as a gate.

### 7.5 Not done, or weaker

- **Trill notation**: done, §8.1.
- **Octave lip slurs** at 8 notes/s or slower, slurred: 0.38 → 0.34. Octave alternations are never split,
  because the tracker's octave flips on held notes look the same. A second attempt, in §8.4, was left out.
- **Sextuplet runs** gained less once tuplets need evidence: in the review's probe, 0.06 → 0.33 dry and
  0.11 under a band.
- **Triplets with 15 ms jitter**: done, §8.2.
- **Tongued fast figures** over 12 notes/s barely improve: pitch alone cannot see a re-articulation. An attack
  cue that holds in a hall was tried in §8.4 and left out.
- **Short takes** with a single tracked beat: done, §8.3.

## 8. Follow-ups

Each step was measured before and after with `fast_notes_bench` on every fast-notes set, with oracle and small0
beats.

The bench now also scores the trill, in three new stages:
- `lead:faithful+tr`: faithful with trills on;
- `built:standard` and `built:easier`: the lead part of a take transcribed at that difficulty, not re-arranged from
  faithful.

It also has two new metrics:
- `trill_kept`: for alternations at a semitone or a whole tone, whether the figure is one trill on the lower pitch,
  with the upper pitch as its auxiliary, covering at least 80 % of the figure;
- `trills`: trill marks per clip. Anywhere but those alternations, these are false trills.

### 8.1 Trill notation (F5)

`brasscribe_music/trills.py`, `core/.../trills.rs`.

**What counts as a trill.** A run of at least 7 notes, alternating between two pitches a semitone or a whole tone
apart.
- The notes touch (gaps of 50 ms or less), no single step is longer than 0.2 s, and the median inter-onset interval is
  0.15 s or less (about 7 notes/s or faster).
- A held last note is the resolution and stays a note of its own.
- A note the quantizer dropped leaves two neighbours on one pitch. At most two notes in a row on one pitch count as
  one turn, so the run still counts.
- Wider alternations (shakes, octave lip slurs) stay written out.

**How it is written.**
- One note on the lower (main) pitch, from the first onset to the last note's end.
- `Note.trill` holds the semitones up to the auxiliary. The Composition JSON writes `trill` only where it is set, and
  the apps' decoders ignore it.

**Where it is applied.**
- **Standard and easier: by default, in two places.**
  - In the transcription, the runs found on the contour-split line replace the notes SwiftF0 merged. The rest of the
    simpler line is unchanged.
  - In the arrangement, written-out alternations are collapsed before the 16th merges. So a faithful composition
    re-arranged at standard or easier gets trills too (the FFI re-arrange path).
- **Faithful: written out, unless asked for.** The option is `--trills` (the transcription CLI and
  `brasscribe-core arrange-layers`), or `trills` in the FFI `ArrangeOptions` and `LayersSongOptions` and in the C API
  options. It is recorded as `arrangement.trills`.

**MusicXML.**
- The mark is `<ornaments><trill-mark/>`, with `<accidental-mark>` only where the key signature does not give the
  auxiliary.
- The auxiliary is spelled from the written part and its key at that bar: the next letter up, at the trill's size.
  Accidentals earlier in the bar are not considered.
- A trill that goes on through ties gets a wavy line from the first note to the last. The line starts inside the trill
  mark's `<ornaments>`, after the mark, because alphaTab 1.8.4 reads a wavy line with no trill mark before it as
  vibrato.
- No `trill-step` is written. alphaTab parses it as a number, but MusicXML's values are words.
- The music21 and Rust writers produce identical files.

**Renderers and playback.**
- alphaTab shows the tr mark: on its 1.8.4 importer, `trillValue` is set and `vibrato` is not. Verovio draws the tr
  mark, the accidental-mark above it and the wavy line over a tied trill (NotationKit
  `trillsShowTheirMarkAccidentalAndWavyLine`).
- Every player trills in 32nds from the main note to the written auxiliary (the next letter up, from the
  accidental-mark, else the key). alphaTab's importer played the written note plus two semitones (four above the main
  note on a B♭ part); Android and Windows now set its trill value from the MusicXML (`AlphaTabMusicXml`), and Apple
  expands the trill in `playbackNotes`. The cases are in `apps/fixtures/ties-and-trills.musicxml`.

**Not covered yet.**
- The faithful trill option is not exposed in the engine's API and schema, and no app has a control for it.
- The apps' managed fallback MusicXML writers (Android `MusicXmlWriter.kt`, Windows' managed path) do not write the
  mark. They run only when the native core is missing.
- The apps' Composition models keep `trill` and `tempo_estimated` when they re-encode a composition for the core:
  Android and Apple through new optional fields, Windows through its extension data.

**Talking score and braille.**
- The talking score (core, engine, Android, Windows, studio) says "trill", or "trill with sharp" and so on; in
  Norwegian "trille", "trille med kryss". The vectors are in `talking-score-vectors.json`, and the spec is §4.6.
- Braille puts the trill sign (dots 2-3-5) before the note, with the auxiliary's accidental before the sign. music21's
  translator drops trills, so `braille.py` adds the sign.

**Parity.**
- 160 `trills` fixtures (with_trills, collapse_trills, and apply_difficulty per mode with trills on, off and by
  default) match exactly in Rust.
- 25 conformance cases on fast-notes clips: standard, easier, faithful `--trills`, and the full band in D♭ and E.

**Results, before → after** (`trill_kept` on the alternations at a semitone or a whole tone):

| Set | Beats | Built at standard or easier | Re-arranged from faithful at standard or easier | Faithful with trills |
|---|---|---|---|---|
| Synthetic (84 clips) | oracle | 0 → 0.39 | 0 → 0.29 | 0 → 0.29 |
| Synthetic (84 clips) | small0 | 0 → 0.39 | 0 → 0.16 | 0 → 0.16 |
| Separated by Mega-53 | oracle | 0 → 0.50 | 0 → 0.33 | 0 → 0.50 |
| Separated by Mega-53 | small0 | 0 → 0.50 | 0 → 0.33 | 0 → 0.50 |

- **By rate** (synthetic, built at standard or easier):

  | Alternation | ≤ 8/s | 9–12/s | > 12/s |
  |---|---|---|---|
  | Slurred | 0.50 | 0.56 | 0.50 |
  | Tongued | 0.20 | 0.50 | 0 |

  The segmentation does not hear tongued alternations above 12/s. A missed alternation is written as before, never as
  a wrong trill.
- **False trills: 0.** None on any must-stay-one-note control, in any render (dry, room, separated); none on the 70 real
  Iowa vibrato notes, dry or in the hall; none on runs, arpeggios, repeated notes, or the minor-3rd, 4th and octave
  alternations.
- **URMP.** One trill in 21 parts, in 20_Pavane at 76.9 s. The annotation has a 12-note semitone alternation (G♯–A)
  there, so it is a real one.
- **ChoraleBricks and Mikkel.** No trill, at any difficulty. The Mikkel golden is byte-identical, and so is every
  faithful output: faithful `written` recall and F1 do not move.
- **The `fast-notes` suite.**
  - `lead:easier.fig_recall` drops, as expected: 0.326 → 0.265 (oracle) and 0.263 → 0.212 (small0). An alternation is
    now one note.
  - The suite now also gates `lead:easier.trill_kept`, `built:easier.trill_kept` and `ctl.trills` (0).

### 8.2 Triplets with timing jitter

With 15 ms of jitter, a triplet 8th lands past the per-beat fit (0.045 beats) in about half the beats. Those beats were
written as 16ths.

**What changed.** The dense quantizer now reads tuplets from runs of beats. A run of at least three consecutive beats
that each hold exactly 3 onsets (or 6) is written as triplets (sextuplets) when both hold:
- over the run, the tuplet's snap error is under a quarter of the plain grid's (16ths, 32nds);
- no onset is more than 0.1 beats off its slot.

Straight 16ths hold exactly three onsets a beat in 16th-16th-8th figures, and a late-played one can look like a
triplet. A run of two was not enough: on the on-device reference clip (the Entertainer, notated in straight 8ths and
16ths only) it turned one such beat after another into triplets. Three beats in a row leave that clip unchanged. Tests
cover 16th-16th-8th, 8th-16th-16th and 16th-8th-16th with 10 and 20 ms of jitter.

**Dense probe** (`research/fastnotes/dense_probe.py`), share of notes on their true slot:

| Case | Before | After |
|---|---|---|
| Triplet 8ths @100, 15 ms jitter | 0.50 | **0.97** |
| Sextuplets @100, 10 ms jitter | 0.93 | 0.94 |
| Every 16th case (exact, 10 and 20 ms jitter, rubato) | unchanged | unchanged |

**Eval sets.**
- Synthetic: the written tuplet share goes 0.04 → 0.05, and written recall 0.436 → 0.437.
- URMP: note F1 goes 0.863 → 0.864. The only part that changes is 42_Arioso trumpet 1, whose score has notated
  triplets: its tuplet share goes 0.030 → 0.052, and its note F1 0.696 → 0.711.
- No other set moves.

**Readability and parity.**
- Mikkel's Solo Cornet stays at 0.3 % tuplets, and the `readability` suite passes unchanged.
- The Mikkel golden and the on-device reference do not change.
- The dense-quantize fixtures are regenerated and match in Rust.

### 8.3 Takes with a single tracked beat

**The problem.** A short, fast take where the beat tracker found one beat, or none, failed the whole transcription.

**What changed.** The layered song builds a grid from the onsets:
- the beat is the multiple of the median inter-onset interval that lies between 75 and 150 BPM, nearest 120;
- it runs through the tracked beat, in bars of 4.

The Composition records `tempo_estimated`, written only when true, and the score prints "tempo?" above the tempo mark.

**Results.**
- `repeat-i0-t150-s8-tongue-samples` with small0 beats used to fail. It is now transcribed at an estimated 99 BPM,
  flagged.
- Python and Rust are identical, with conformance cases for one beat and for none.
- Takes with two or more beats do not change: every other clip and the Mikkel golden are identical.

### 8.4 Tried and left out

Both attempts were bounded. Both are left out because the controls rose.

**Octave lip slurs.**
- **The rule tried.** Split a note whose plateaus alternate by exactly an octave when every plateau holds 5 frames
  and Basic Pitch has a note at the plateau's own pitch on at least 60 % of them (a harmonic confirmation, which the
  contour cannot give itself).
- **The gain.** Slurred alternation at 9–12/s: alternations kept 0.333 → 0.356 (oracle).
- **The cost.**
  - Doit extras 0.19 → 0.31.
  - Fall extras 0.46 → 0.63.
  - Slow-slur recall 0.89 → 0.86.
  - Chorale note F1 0.722 → 0.720.
- **Why.** Basic Pitch also hears the upper partial on falls and doits, so it is not an independent confirmation
  there.

**Tongued figures over 12 notes/s.**
- **The cue tried.** An attack on the contour's loudness: a rise of 9 dB within 32 ms, right after a dip of 6 dB below
  the previous 100 ms.
- **What the cue finds.**
  - False cues: none on the 35 real Iowa vibrato notes, dry or in the hall. A 3 dB rise gives 5 per note in the hall.
  - Tongued onsets up to 12/s: 0.94 found dry and 0.82 in the room.
  - Tongued onsets above 12/s: 0.45.
  - SoundFont renders: none, because their notes have no attack.
- **What it does in the solo path**, splitting SwiftF0 notes at those attacks:
  - Repeated tongued notes above 12/s: 0.103 → 0.127 (small0 only).
  - Tongued alternations and runs above 12/s: unchanged. There, the line and the quantizer are the limit, not the
    onsets.
  - Rip extras: 0.44 → 0.50.
- **For a next attempt.** The cue holds in a hall. It is worth trying again together with a finer line and grid at
  those rates.
